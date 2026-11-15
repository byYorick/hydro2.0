"""EC command sequence execution through explicit dispatch and failure-policy ports."""

from __future__ import annotations

import json
from dataclasses import dataclass, replace
from datetime import datetime
from typing import Any, Awaitable, Callable, Mapping, Sequence

from ae3lite.application.dto.stage_outcome import StageOutcome
from ae3lite.domain.entities.planned_command import PlannedCommand
from ae3lite.domain.entities.workflow_state import CorrectionState
from ae3lite.domain.errors import TaskExecutionError
from ae3lite.domain.services.ec_batch_failure import first_failed_ec_index
from ae3lite.infrastructure.metrics import IRRIGATION_EC_COMPONENT_DOSE


@dataclass(frozen=True)
class EcDoseSequence:
    items: list[dict[str, Any]]
    single_meta: dict[str, Any] | None


@dataclass(frozen=True)
class EcDoseExecution:
    correction: CorrectionState
    task: Any
    batch_result: Mapping[str, Any]


def parse_ec_dose_sequence(corr: CorrectionState) -> EcDoseSequence:
    seq: list[dict[str, Any]] = []
    ec_single_meta: dict[str, Any] | None = None
    if corr.ec_dose_sequence_json:
        try:
            raw = json.loads(corr.ec_dose_sequence_json)
            if isinstance(raw, list):
                seq = list(raw)
            elif isinstance(raw, dict):
                if raw.get("_kind") == "ph_dose_meta":
                    seq = []
                else:
                    ec_single_meta = dict(raw)
                    seq = [ec_single_meta]
            else:
                raise TaskExecutionError("corr_dose_ec_bad_sequence", "EC dose sequence JSON должен быть списком")
        except Exception as exc:
            if isinstance(exc, TaskExecutionError):
                raise
            raise TaskExecutionError("corr_dose_ec_bad_sequence", "EC dose sequence JSON некорректен")
    if seq:
        for item in seq:
            if not isinstance(item, dict):
                raise TaskExecutionError("corr_dose_ec_bad_sequence", "Элемент EC dose sequence должен быть объектом")
            if not str(item.get("node_uid") or "").strip():
                raise TaskExecutionError("corr_dose_ec_bad_sequence", "В EC dose sequence отсутствует node_uid")
            if not str(item.get("channel") or "").strip():
                raise TaskExecutionError("corr_dose_ec_bad_sequence", "В EC dose sequence отсутствует channel")
            try:
                ml = float(item.get("amount_ml"))
            except (TypeError, ValueError):
                ml = 0.0
            if ml <= 0:
                raise TaskExecutionError(
                    "corr_dose_ec_bad_sequence", "В EC dose sequence значение amount_ml должно быть > 0"
                )
    else:
        if (
            not corr.ec_node_uid
            or not corr.ec_channel
            or not corr.ec_duration_ms
            or corr.ec_amount_ml is None
            or corr.ec_amount_ml <= 0.0
        ):
            raise TaskExecutionError(
                "corr_dose_ec_missing_plan",
                (
                    "Отсутствует EC dose plan "
                    f"(node={corr.ec_node_uid}, ch={corr.ec_channel}, ms={corr.ec_duration_ms}, "
                    f"ml={corr.ec_amount_ml})"
                ),
            )
    return EcDoseSequence(items=seq, single_meta=ec_single_meta)


class CorrectionEcDoseExecutor:
    """Dispatches one sequential component or one gateway-serialized batch per call."""

    def __init__(
        self,
        *,
        dispatch_fn: Callable[..., Awaitable[Mapping[str, Any]]],
        partial_failure_fn: Callable[..., Awaitable[StageOutcome | None]],
        raise_error_fn: Callable[..., Awaitable[None]],
        calibration_fn: Callable[..., float],
        feedback_fn: Callable[..., tuple[float, int, bool]],
        first_node_uid_fn: Callable[[Sequence[Any]], str | None],
    ) -> None:
        self._dispatch = dispatch_fn
        self._handle_partial_failure = partial_failure_fn
        self._raise_error = raise_error_fn
        self._calibration = calibration_fn
        self._feedback = feedback_fn
        self._first_node_uid = first_node_uid_fn

    async def execute(
        self,
        *,
        task: Any,
        current_task: Any,
        plan: Any,
        corr: CorrectionState,
        now: datetime,
        seq: Sequence[Mapping[str, Any]],
        is_parallel: bool,
        actuators: Mapping[str, Any],
        dose_context: Mapping[str, Any],
    ) -> EcDoseExecution | StageOutcome:
        result: Mapping[str, Any] = {}
        if seq and is_parallel:
            # multi_parallel: отправляем ВСЕ dose-команды за один batch.
            # Gateway исполняет batch по одной команде и ждёт DONE перед следующей.
            batch_cmds: list[PlannedCommand] = []
            for idx, item in enumerate(seq):
                comp = str(item.get("component") or "").strip().lower()
                if comp:
                    IRRIGATION_EC_COMPONENT_DOSE.labels(topology=task.topology, component=comp).inc()
                batch_cmds.append(
                    PlannedCommand(
                        step_no=idx + 1,
                        node_uid=str(item["node_uid"]),
                        channel=str(item["channel"]),
                        payload={
                            "cmd": "dose",
                            "_ae3_dose_context": dose_context,
                            "params": {
                                "ml": float(item["amount_ml"]),
                                "duration_ms": int(item["duration_ms"]),
                            },
                        },
                    )
                )
            try:
                result = await self._dispatch(
                    task=current_task,
                    commands=tuple(batch_cmds),
                    checked=False,
                    now=now,
                )
            except TaskExecutionError as exc:
                partial = await self._handle_partial_failure(
                    task=current_task,
                    plan=plan,
                    corr=corr,
                    seq=seq,
                    mode="multi_parallel",
                    failed_index=0,
                    error_code=exc.code,
                    error_message=str(exc),
                    batch_result=None,
                )
                if partial is not None:
                    return partial
                raise
            current_task = result.get("task") or current_task
            if not result.get("success"):
                failed_index = first_failed_ec_index(
                    seq=seq,
                    batch_result=result,
                )
                partial = await self._handle_partial_failure(
                    task=current_task,
                    plan=plan,
                    corr=corr,
                    seq=seq,
                    mode="multi_parallel",
                    failed_index=failed_index,
                    error_code=str(result.get("error_code") or "ec_batch_command_failed"),
                    error_message=str(result.get("error_message") or "EC batch command failed"),
                    batch_result=result,
                )
                if partial is not None:
                    return partial
                await self._raise_error(
                    task=current_task,
                    error_code=str(result.get("error_code") or "ec_batch_command_failed"),
                    error_message=str(result.get("error_message") or "EC batch command failed"),
                    node_uid=self._first_node_uid(tuple(batch_cmds)),
                    deadline_kind=(
                        str(result.get("deadline_kind")) if result.get("deadline_kind") is not None else None
                    ),
                )
            corr = replace(corr, ec_current_seq_index=len(seq))
        elif seq:
            # multi_sequential: отправляем по ОДНОМУ компоненту за вызов,
            # возобновляясь через ec_current_seq_index.
            start_idx = int(getattr(corr, "ec_current_seq_index", 0) or 0)
            if start_idx < 0:
                start_idx = 0
            if start_idx >= len(seq):
                start_idx = len(seq)

            if start_idx < len(seq):
                item = seq[start_idx]
                comp = str(item.get("component") or "").strip().lower()
                if comp:
                    IRRIGATION_EC_COMPONENT_DOSE.labels(topology=task.topology, component=comp).inc()
                cmd = PlannedCommand(
                    step_no=start_idx + 1,
                    node_uid=str(item["node_uid"]),
                    channel=str(item["channel"]),
                    payload={
                        "cmd": "dose",
                        "_ae3_dose_context": dose_context,
                        "params": {
                            "ml": float(item["amount_ml"]),
                            "duration_ms": int(item["duration_ms"]),
                        },
                    },
                )
                try:
                    result = await self._dispatch(
                        task=current_task,
                        commands=(cmd,),
                        checked=False,
                        now=now,
                    )
                except TaskExecutionError as exc:
                    partial = await self._handle_partial_failure(
                        task=current_task,
                        plan=plan,
                        corr=corr,
                        seq=seq,
                        mode="multi_sequential",
                        failed_index=start_idx,
                        error_code=exc.code,
                        error_message=str(exc),
                        batch_result=None,
                    )
                    if partial is not None:
                        return partial
                    raise
                current_task = result.get("task") or current_task
                if not result.get("success"):
                    partial = await self._handle_partial_failure(
                        task=current_task,
                        plan=plan,
                        corr=corr,
                        seq=seq,
                        mode="multi_sequential",
                        failed_index=start_idx,
                        error_code=str(result.get("error_code") or "ec_batch_command_failed"),
                        error_message=str(result.get("error_message") or "EC batch command failed"),
                        batch_result=result,
                    )
                    if partial is not None:
                        return partial
                    await self._raise_error(
                        task=current_task,
                        error_code=str(result.get("error_code") or "ec_batch_command_failed"),
                        error_message=str(result.get("error_message") or "EC batch command failed"),
                        node_uid=str(item.get("node_uid") or "") or None,
                        deadline_kind=(
                            str(result.get("deadline_kind")) if result.get("deadline_kind") is not None else None
                        ),
                    )

                planned_ml = float(item.get("amount_ml") or 0.0)
                planned_ms = int(item.get("duration_ms") or 0)
                ml_per_sec = self._calibration(actuators=actuators, item=item)
                actual_ml, actual_ms, _ = self._feedback(
                    planned_ml=planned_ml,
                    planned_duration_ms=planned_ms,
                    ml_per_sec=ml_per_sec,
                    batch_result=result,
                )
                corr = replace(
                    corr,
                    ec_amount_ml=round(max(0.0, float(corr.ec_amount_ml or 0.0) - planned_ml + actual_ml), 4),
                    ec_duration_ms=max(
                        0,
                        int(corr.ec_duration_ms or 0) - planned_ms + actual_ms,
                    ),
                )

                next_idx = start_idx + 1
                if next_idx < len(seq):
                    # Persist progress and immediately continue with the next component.
                    return StageOutcome(
                        kind="enter_correction",
                        correction=replace(corr, ec_current_seq_index=next_idx),
                        due_delay_sec=0,
                        task_override=current_task if current_task is not task else None,
                    )

                # Sequence complete; continue with standard post-dose hold window below.
                corr = replace(corr, ec_current_seq_index=next_idx)
            else:
                # Already complete (resume after crash) — treat as done and proceed.
                corr = replace(corr, ec_current_seq_index=start_idx)
        else:
            cmd = PlannedCommand(
                step_no=1,
                node_uid=corr.ec_node_uid,
                channel=corr.ec_channel,
                payload={
                    "cmd": "dose",
                    "_ae3_dose_context": dose_context,
                    "params": {
                        "ml": corr.ec_amount_ml,
                        "duration_ms": int(corr.ec_duration_ms or 0),
                    },
                },
            )
            result = await self._dispatch(
                task=current_task,
                commands=(cmd,),
                now=now,
                checked=True,
            )
            current_task = result.get("task") or current_task

        return EcDoseExecution(correction=corr, task=current_task, batch_result=result)
