"""Dose policy boundaries: priority, persisted metadata and terminal accounting."""

from __future__ import annotations

import asyncio
import json
from dataclasses import replace
from datetime import datetime
from unittest.mock import AsyncMock, Mock

import pytest

from ae3lite.application.services import correction_dose_accounting as accounting
from ae3lite.domain.entities.workflow_state import CorrectionState
from ae3lite.domain.services.correction_dose_routing import route_dose_plan
from ae3lite.domain.services.correction_planner import DosePlan, EcDoseStep


def correction(**changes):
    corr = CorrectionState.build_default(
        corr_step='corr_check',
        max_attempts=5,
        ec_max_attempts=5,
        ph_max_attempts=5,
        activated_here=False,
        stabilization_sec=60,
        return_stage_success='ready',
        return_stage_fail='failed',
    )
    return replace(corr, **changes)


@pytest.mark.parametrize(
    ('pending_ph', 'plan', 'step', 'action', 'reason'),
    [
        (False, DosePlan(needs_ec=True, needs_ph_up=True), 'corr_dose_ec', 'ec', 'ec_first_in_window'),
        (
            True,
            DosePlan(needs_ec=True, needs_ph_down=True),
            'corr_dose_ph',
            'ph_down',
            'prioritize_pending_ph_after_ec_observe',
        ),
        (True, DosePlan(needs_ec=True), 'corr_dose_ec', 'ec', 'ec_only_needed'),
        (False, DosePlan(needs_ph_up=True), 'corr_dose_ph', 'ph_up', 'ph_raise_needed'),
        (False, DosePlan(needs_ph_down=True), 'corr_dose_ph', 'ph_down', 'ph_lower_needed'),
    ],
)
def test_routing_preserves_pending_ph_priority(pending_ph, plan, step, action, reason):
    corr = correction(needs_ph_up=pending_ph)
    result = route_dose_plan(corr=corr, dose_plan=plan)
    assert (result.correction.corr_step, result.selected_action, result.decision_reason) == (step, action, reason)
    assert corr.corr_step == 'corr_check'
    assert corr.needs_ph_up is pending_ph


def test_routing_without_any_dose_returns_no_action():
    assert route_dose_plan(corr=correction(), dose_plan=DosePlan()) is None


def test_multi_ec_metadata_preserves_order_and_explicit_requested_volume():
    corr = correction(ec_current_seq_index=2, attempt=3, pipeline_phase='npk', needs_ph_down=True)
    plan = DosePlan(
        needs_ec=True,
        ec_dose_sequence=(
            EcDoseStep('calcium', 'node-ca', 'pump-ca', 1.0, 500, requested_ml=0.0),
            EcDoseStep('npk', 'node-npk', 'pump-npk', 2.0, 1000),
        ),
    )
    result = route_dose_plan(corr=corr, dose_plan=plan)
    meta = json.loads(result.correction.ec_dose_sequence_json)
    assert [row['component'] for row in meta] == ['calcium', 'npk']
    assert [row['requested_ml'] for row in meta] == [0.0, 2.0]
    assert [row['duration_ms'] for row in meta] == [500, 1000]
    assert result.correction.ec_current_seq_index == 0
    assert result.correction.attempt == 3
    assert result.correction.pipeline_phase == 'npk'
    assert not result.correction.needs_ph_down
    assert corr.ec_current_seq_index == 2


def test_single_ec_and_clamped_ph_preserve_legacy_metadata_shapes():
    ec = route_dose_plan(
        corr=correction(),
        dose_plan=DosePlan(
            needs_ec=True,
            ec_amount_ml=2,
            ec_duration_ms=1000,
            ec_node_uid='ec-node',
            ec_channel='ec',
        ),
    )
    assert json.loads(ec.correction.ec_dose_sequence_json) == dict(
        component='single',
        node_uid='ec-node',
        channel='ec',
        amount_ml=2,
        requested_ml=2,
        duration_ms=1000,
    )
    ph = route_dose_plan(
        corr=correction(),
        dose_plan=DosePlan(
            needs_ph_up=True,
            ph_amount_ml=1,
            ph_requested_ml=3,
            ph_duration_ms=500,
        ),
    )
    assert json.loads(ph.correction.ec_dose_sequence_json) == dict(
        _kind='ph_dose_meta',
        requested_ml=3,
        effective_ml=1,
    )


@pytest.mark.parametrize(
    'actuator',
    [None, {}, {'calibration': None}, {'calibration': {'ml_per_sec': 'invalid'}}, {'calibration': {'ml_per_sec': -2}}],
)
def test_missing_or_invalid_calibration_produces_no_flow(actuator):
    assert accounting.ml_per_sec_for_actuator(actuator) == 0.0


def test_ec_component_calibration_and_generic_fallback_stay_separate():
    actuators = dict(
        ec={'calibration': {'ml_per_sec': 9}},
        ec_actuators={
            'calcium': {'calibration': {'ml_per_sec': '2.5'}},
            'ec_npk': {'calibration': {'ml_per_sec': 3}},
        },
    )
    assert accounting.ml_per_sec_for_ec_item(actuators=actuators, item={'component': ' Calcium '}) == 2.5
    assert accounting.ml_per_sec_for_ec_item(actuators=actuators, item={'component': 'npk'}) == 3
    assert accounting.ml_per_sec_for_ec_item(actuators=actuators, item={'component': 'unknown'}) == 9


def test_feedback_uses_matching_batch_status_and_never_exceeds_planned_volume():
    result = dict(
        command_statuses=[
            {'response_details': {'duration_ms': 500, 'duration_limited': True}},
            {'response_details': {'duration_ms': 1500, 'duration_limited': True}},
        ]
    )
    args = dict(planned_ml=2, planned_duration_ms=2000, ml_per_sec=2, batch_result=result)
    assert accounting.resolve_dose_outcome(**args, status_index=0) == (1.0, 500, True)
    assert accounting.resolve_dose_outcome(**args, status_index=1) == (2.0, 1500, True)
    assert accounting.resolve_dose_outcome(**args, status_index=2) == (2.0, 2000, False)


@pytest.mark.asyncio
async def test_marker_only_receives_completed_doses_with_a_command_id():
    mark, logger = AsyncMock(), Mock()
    now = datetime(2026, 11, 14)
    statuses = [
        None,
        {},
        {'ae_command_id': 1, 'cmd': 'dose', 'terminal_status': 'DONE'},
        {'ae_command_id': 2, 'cmd': 'dose', 'terminal_status': 'TIMEOUT'},
        {'ae_command_id': 3, 'cmd': 'stop', 'terminal_status': 'DONE'},
        {'ae_command_id': 4, 'cmd': 'dose', 'terminal_status': 'ACK'},
        {'ae_command_id': 5, 'terminal_status': 'done'},
    ]
    await accounting.mark_accounted_dose_commands(
        batch_result={'command_statuses': statuses},
        now=now,
        mark_dose_accounted=mark,
        logger=logger,
    )
    assert [call.kwargs for call in mark.await_args_list] == [
        dict(ae_command_id=command_id, now=now) for command_id in (1, 5)
    ]
    logger.warning.assert_not_called()


@pytest.mark.asyncio
async def test_marker_failure_leaves_repair_possible_and_does_not_hide_later_doses():
    mark = AsyncMock(side_effect=[OSError('database unavailable'), True])
    logger = Mock()
    await accounting.mark_accounted_dose_commands(
        batch_result={'command_statuses': [dict(ae_command_id=i, cmd='dose', terminal_status='DONE') for i in (1, 2)]},
        now=datetime(2026, 11, 14),
        mark_dose_accounted=mark,
        logger=logger,
    )
    assert mark.await_count == 2
    logger.warning.assert_called_once()


@pytest.mark.asyncio
async def test_marker_cancellation_propagates_without_accounting_later_commands():
    mark = AsyncMock(side_effect=asyncio.CancelledError)
    logger = Mock()
    with pytest.raises(asyncio.CancelledError):
        await accounting.mark_accounted_dose_commands(
            batch_result={
                'command_statuses': [dict(ae_command_id=i, cmd='dose', terminal_status='DONE') for i in (1, 2)]
            },
            now=datetime(2026, 11, 14),
            mark_dose_accounted=mark,
            logger=logger,
        )
    assert mark.await_count == 1
    logger.warning.assert_not_called()
