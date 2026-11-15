"""EC execution boundaries: resume position, command shape and fail-closed exits."""

from __future__ import annotations

import asyncio
import json
from dataclasses import replace
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from ae3lite.application.dto.stage_outcome import StageOutcome
from ae3lite.application.services.correction_dose_accounting import resolve_dose_outcome
from ae3lite.application.services.correction_ec_dose_executor import (
    CorrectionEcDoseExecutor,
    EcDoseExecution,
    parse_ec_dose_sequence,
)
from ae3lite.domain.entities.workflow_state import CorrectionState
from ae3lite.domain.errors import TaskExecutionError
from ae3lite.domain.services.ec_batch_failure import (
    describe_partial_ec_failure,
    first_failed_ec_index,
)

NOW = datetime(2026, 11, 15, 12)
SEQ = [
    dict(component='calcium', node_uid='node-ca', channel='ca', amount_ml=1, duration_ms=1000),
    dict(component='npk', node_uid='node-npk', channel='npk', amount_ml=2, duration_ms=2000),
    dict(component='micro', node_uid='node-micro', channel='micro', amount_ml=3, duration_ms=3000),
]


def correction(**updates):
    corr = CorrectionState.build_default(
        corr_step='corr_dose_ec',
        max_attempts=5,
        ec_max_attempts=5,
        ph_max_attempts=5,
        activated_here=False,
        stabilization_sec=60,
        return_stage_success='ready',
        return_stage_fail='failed',
    )
    corr = replace(
        corr,
        needs_ec=True,
        ec_node_uid='node-ec',
        ec_channel='ec',
        ec_amount_ml=6,
        ec_duration_ms=6000,
        ec_component='multi_sequential',
    )
    return replace(corr, **updates)


def setup_executor():
    dispatch = AsyncMock(return_value={'success': True})
    partial = AsyncMock(return_value=None)
    error = AsyncMock(side_effect=TaskExecutionError('execution_failed', 'failed'))
    executor = CorrectionEcDoseExecutor(
        dispatch_fn=dispatch,
        partial_failure_fn=partial,
        raise_error_fn=error,
        calibration_fn=lambda **kwargs: 1.0,
        feedback_fn=resolve_dose_outcome,
        first_node_uid_fn=lambda commands: commands[0].node_uid,
    )
    task = SimpleNamespace(id=1, zone_id=7, topology='two_tank')
    args = dict(
        task=task,
        current_task=task,
        plan=object(),
        corr=correction(),
        now=NOW,
        seq=SEQ,
        is_parallel=False,
        actuators={},
        dose_context={'pid_type': 'ec', 'last_correction_kind': 'ec', 'hold_sec': 12},
    )
    return executor, dispatch, partial, error, args


@pytest.mark.parametrize('index', [-2, 0, 1])
@pytest.mark.asyncio
async def test_sequential_call_dispatches_only_resume_component_and_preserves_updated_task(index):
    executor, dispatch, partial, error, args = setup_executor()
    args['corr'] = correction(ec_current_seq_index=index)
    updated_task = SimpleNamespace(id=1, zone_id=7, topology='two_tank', generation=2)
    dispatch.return_value = dict(success=True, task=updated_task)
    result = await executor.execute(**args)
    selected_index = max(0, index)
    (command,) = dispatch.await_args.kwargs['commands']
    assert dispatch.await_count == 1
    assert dispatch.await_args.kwargs['checked'] is False
    assert (command.step_no, command.node_uid) == (selected_index + 1, SEQ[selected_index]['node_uid'])
    assert command.payload == dict(
        cmd='dose',
        _ae3_dose_context=args['dose_context'],
        params=dict(ml=float(SEQ[selected_index]['amount_ml']), duration_ms=SEQ[selected_index]['duration_ms']),
    )
    assert isinstance(result, StageOutcome)
    assert result.correction.ec_current_seq_index == selected_index + 1
    assert result.task_override is updated_task
    assert args['corr'].ec_current_seq_index == index
    partial.assert_not_awaited()
    error.assert_not_awaited()


@pytest.mark.asyncio
async def test_feedback_adjusts_sequential_progress_before_returning_next_component():
    executor, dispatch, _partial, _error, args = setup_executor()
    dispatch.return_value = dict(
        success=True,
        command_statuses=[
            {
                'terminal_status': 'DONE',
                'response_details': {'duration_ms': 500, 'duration_limited': True},
            }
        ],
    )
    result = await executor.execute(**args)
    assert result.correction.ec_amount_ml == 5.5
    assert result.correction.ec_duration_ms == 5500
    assert result.correction.ec_current_seq_index == 1


@pytest.mark.parametrize('index', [3, 20])
@pytest.mark.asyncio
async def test_completed_sequence_never_dispatches_again(index):
    executor, dispatch, partial, error, args = setup_executor()
    args['corr'] = correction(ec_current_seq_index=index)
    result = await executor.execute(**args)
    assert isinstance(result, EcDoseExecution)
    assert result.correction.ec_current_seq_index == len(SEQ)
    assert result.batch_result == {}
    dispatch.assert_not_awaited()
    partial.assert_not_awaited()
    error.assert_not_awaited()


@pytest.mark.asyncio
async def test_logical_parallel_submits_one_ordered_batch_and_keeps_reconciled_task():
    executor, dispatch, _partial, _error, args = setup_executor()
    args['is_parallel'] = True
    updated = SimpleNamespace(id=1)
    dispatch.return_value = dict(success=True, task=updated)
    result = await executor.execute(**args)
    assert isinstance(result, EcDoseExecution)
    assert result.task is updated
    assert result.correction.ec_current_seq_index == 3
    commands = dispatch.await_args.kwargs['commands']
    assert [(c.step_no, c.node_uid) for c in commands] == [(i + 1, row['node_uid']) for i, row in enumerate(SEQ)]
    assert dispatch.await_count == 1
    assert all(c.payload['_ae3_dose_context'] == args['dose_context'] for c in commands)


@pytest.mark.asyncio
async def test_single_dose_uses_checked_dispatch():
    executor, dispatch, _partial, _error, args = setup_executor()
    args['seq'] = []
    result = await executor.execute(**args)
    assert isinstance(result, EcDoseExecution)
    assert dispatch.await_args.kwargs['checked'] is True
    (command,) = dispatch.await_args.kwargs['commands']
    assert command.payload['params'] == {'ml': 6, 'duration_ms': 6000}


@pytest.mark.asyncio
async def test_partial_batch_returns_failure_policy_outcome_without_advancing_sequence():
    executor, dispatch, partial, error, args = setup_executor()
    args['is_parallel'] = True
    updated = SimpleNamespace(id=1)
    dispatch.return_value = dict(
        success=False,
        task=updated,
        error_code='timeout',
        command_statuses=[{'terminal_status': 'DONE'}, {'terminal_status': 'TIMEOUT'}],
    )
    sentinel = StageOutcome(kind='exit_correction', correction=replace(args['corr'], outcome_success=False))
    partial.return_value = sentinel
    assert await executor.execute(**args) is sentinel
    assert partial.await_args.kwargs['failed_index'] == 1
    assert partial.await_args.kwargs['task'] is updated
    assert args['corr'].ec_current_seq_index == 0
    error.assert_not_awaited()


@pytest.mark.asyncio
async def test_non_partial_failure_retains_deadline_kind_for_error_handler():
    executor, dispatch, partial, error, args = setup_executor()
    args['is_parallel'] = True
    dispatch.return_value = dict(
        success=False, error_code='admission_refused', deadline_kind='stage_admission', command_statuses=[]
    )
    with pytest.raises(TaskExecutionError):
        await executor.execute(**args)
    assert partial.await_count == 1
    assert error.await_args.kwargs['deadline_kind'] == 'stage_admission'
    assert error.await_args.kwargs['node_uid'] == 'node-ca'


@pytest.mark.asyncio
async def test_poll_deadline_exception_propagates_if_partial_policy_declines_it():
    executor, dispatch, partial, error, args = setup_executor()
    args['corr'] = correction(ec_current_seq_index=1)
    original = TaskExecutionError('ae3_command_poll_deadline_exceeded', 'expired')
    dispatch.side_effect = original
    with pytest.raises(TaskExecutionError) as caught:
        await executor.execute(**args)
    assert caught.value is original
    assert partial.await_args.kwargs['failed_index'] == 1
    error.assert_not_awaited()


@pytest.mark.asyncio
async def test_cancellation_never_becomes_partial_failure_or_retries():
    executor, dispatch, partial, error, args = setup_executor()
    dispatch.side_effect = asyncio.CancelledError
    with pytest.raises(asyncio.CancelledError):
        await executor.execute(**args)
    assert dispatch.await_count == 1
    assert args['corr'].ec_current_seq_index == 0
    partial.assert_not_awaited()
    error.assert_not_awaited()


@pytest.mark.asyncio
async def test_shared_executor_keeps_concurrent_task_contexts_separate():
    executor, dispatch, _partial, _error, first = setup_executor()
    second_task = SimpleNamespace(id=2, zone_id=8, topology='two_tank')
    second = dict(
        first,
        task=second_task,
        current_task=second_task,
        corr=correction(ec_amount_ml=4),
        dose_context={'pid_type': 'ec', 'hold_sec': 27},
    )
    first = dict(first, is_parallel=True, seq=SEQ[:1])
    second = dict(second, is_parallel=True, seq=SEQ[:1])
    entered = asyncio.Event()
    seen = {}

    async def run_batch(**kwargs):
        seen[kwargs['task'].id] = kwargs['commands'][0].payload['_ae3_dose_context']
        if len(seen) == 2:
            entered.set()
        await entered.wait()
        return {'success': True, 'task': kwargs['task']}

    dispatch.side_effect = run_batch
    results = await asyncio.wait_for(
        asyncio.gather(executor.execute(**first), executor.execute(**second)),
        timeout=1,
    )
    assert [(r.task.id, r.correction.ec_amount_ml) for r in results] == [(1, 6), (2, 4)]
    assert seen == {1: first['dose_context'], 2: second['dose_context']}


@pytest.mark.parametrize(
    'raw',
    [
        'not-json',
        '42',
        '[null]',
        '[{}]',
        '[{"node_uid":"n","channel":"c","amount_ml":0}]',
        '[{"node_uid":"n","channel":"c","amount_ml":"bad"}]',
    ],
)
def test_invalid_sequence_fails_before_executor_dispatch(raw):
    with pytest.raises(TaskExecutionError) as caught:
        parse_ec_dose_sequence(correction(ec_dose_sequence_json=raw))
    assert caught.value.code == 'corr_dose_ec_bad_sequence'


def test_parser_preserves_single_ec_metadata_and_skips_ph_metadata():
    data = dict(SEQ[0], requested_ml=4)
    result = parse_ec_dose_sequence(correction(ec_dose_sequence_json=json.dumps(data)))
    assert result.items == [data] and result.single_meta == data
    result = parse_ec_dose_sequence(correction(ec_dose_sequence_json='{"_kind":"ph_dose_meta"}'))
    assert result.items == [] and result.single_meta is None


@pytest.mark.parametrize('mode', ['multi_sequential', 'multi_parallel'])
def test_poll_deadline_is_never_classified_as_partial_degrade(mode):
    assert (
        describe_partial_ec_failure(
            seq=SEQ,
            mode=mode,
            failed_index=1,
            error_code='ae3_command_poll_deadline_exceeded',
            batch_result={'command_statuses': [{'terminal_status': 'DONE'}, {'terminal_status': 'TIMEOUT'}]},
        )
        is None
    )


def test_partial_descriptor_partitions_components_and_clamps_bad_index():
    result = describe_partial_ec_failure(
        seq=SEQ, mode='multi_sequential', failed_index=50, error_code='timeout', batch_result=None
    )
    assert result.failed_index == 2
    assert result.successful_components == ['calcium', 'npk']
    assert result.failed_component == 'micro'
    assert result.remaining_components == []
    assert (
        describe_partial_ec_failure(
            seq=SEQ, mode='multi_sequential', failed_index=-5, error_code='timeout', batch_result=None
        )
        is None
    )


def test_parallel_failure_without_confirmed_prior_success_is_not_partial():
    assert (
        describe_partial_ec_failure(
            seq=SEQ,
            mode='multi_parallel',
            failed_index=1,
            error_code='timeout',
            batch_result={'command_statuses': [{'terminal_status': 'ERROR'}, {'terminal_status': 'TIMEOUT'}]},
        )
        is None
    )


def test_failed_index_selects_first_failure_not_last_status():
    assert (
        first_failed_ec_index(
            seq=SEQ,
            batch_result={
                'command_statuses': [
                    {'terminal_status': 'DONE'},
                    {'terminal_status': 'TIMEOUT'},
                    {'terminal_status': 'ERROR'},
                ]
            },
        )
        == 1
    )
