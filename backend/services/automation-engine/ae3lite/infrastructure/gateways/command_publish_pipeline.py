"""Общий publish-pipeline AE3-Lite: ae_commands → HL → legacy link."""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Mapping, Optional

from ae3lite.domain.entities import PlannedCommand
from ae3lite.domain.errors import CommandPublishError
from ae3lite.infrastructure.metrics import (
    COMMAND_CMD_ID_REUSED,
    COMMAND_DISPATCH_DURATION,
    COMMAND_DISPATCHED,
    COMMAND_PUBLISH_REDRIVEN,
)

logger = logging.getLogger(__name__)

_LEGACY_RESOLVE_ATTEMPTS = 3
_LEGACY_RESOLVE_DELAY_SEC = 0.05

_DEFINITE_NOT_PUBLISHED_MARKERS = (
    "hl_circuit_open",
    "не удалось определить greenhouse_uid",
    "plannedcommand должен содержать",
    "исчезла во время вставки",
)
_AMBIGUOUS_PUBLISH_MARKERS = (
    "timeout",
    "readtimeout",
    "connecttimeout",
    "connection",
    "transport",
    "temporary_unavailable",
    "http 5",
    "published_but_status",
    "некорректный json",
    "не содержит data.command_id",
)


def is_publish_outcome_unknown(exc: Exception) -> bool:
    """True when HL may have accepted the command despite the transport-layer error."""
    message = str(exc).strip().lower() or type(exc).__name__.lower()
    for marker in _DEFINITE_NOT_PUBLISHED_MARKERS:
        if marker in message:
            return False
    for marker in _AMBIGUOUS_PUBLISH_MARKERS:
        if marker in message:
            return True
    if isinstance(exc, CommandPublishError):
        return True
    return True


def build_cmd_id(*, task_id: int, zone_id: int, step_no: int) -> str:
    return f"ae3-t{task_id}-z{zone_id}-s{step_no}"


def build_planner_step(
    *,
    stage: str,
    seq_index: int,
    corr_step: str | None = None,
    component: str | None = None,
    explicit: str | None = None,
) -> str | None:
    if explicit is not None and str(explicit).strip():
        return str(explicit).strip()[:160]
    normalized_stage = str(stage or "").strip() or "unknown"
    normalized_corr = str(corr_step or "").strip()
    if normalized_corr:
        normalized_component = str(component or seq_index).strip() or str(seq_index)
        return f"{normalized_stage}:{normalized_corr}:{normalized_component}"[:160]
    return f"{normalized_stage}:{seq_index}"[:160]


def extract_corr_step(task: Any) -> str | None:
    correction = getattr(task, "correction", None)
    if correction is not None:
        value = str(getattr(correction, "corr_step", "") or "").strip()
        return value or None
    workflow = getattr(task, "workflow", None)
    if workflow is not None:
        value = str(getattr(workflow, "corr_step", "") or "").strip()
        return value or None
    return None


def planner_step_for_command(*, task: Any, command: PlannedCommand, seq_index: int) -> str | None:
    explicit = getattr(command, "planner_step", None)
    if explicit is not None and str(explicit).strip():
        return str(explicit).strip()[:160]
    stage = str(getattr(task, "current_stage", "") or "")
    channel = str(command.channel or "").strip() or "unknown"
    corr_step = extract_corr_step(task)
    if corr_step:
        return build_planner_step(
            stage=stage,
            seq_index=seq_index,
            corr_step=corr_step,
            component=channel,
        )
    normalized_stage = stage.strip() or "unknown"
    return f"{normalized_stage}:{seq_index}:{channel}"[:160]


@dataclass(frozen=True)
class CommandPublishResult:
    ae_command_id: int
    step_no: int
    cmd_id: str
    published_cmd_id: str
    cmd_name: str
    params: Mapping[str, Any]
    external_id: str | None
    cmd_id_reused: bool
    redriven: bool


class CommandPublishPipeline:
    """Единая реализация INSERT/publish/link для gateway и use-case."""

    def __init__(self, *, command_repository: Any, history_logger_client: Any) -> None:
        self._command_repository = command_repository
        self._history_logger_client = history_logger_client

    async def allocate_command(
        self,
        *,
        task: Any,
        command: PlannedCommand,
        command_payload: Mapping[str, Any],
        now: datetime,
        planner_step: str | None,
    ) -> tuple[int, int, str, bool, str] | None:
        allocate = getattr(self._command_repository, "allocate_and_create_pending", None)
        stage_name = str(getattr(task, "current_stage", "") or "") or None
        if callable(allocate):
            allocated = await allocate(
                task_id=task.id,
                zone_id=int(task.zone_id),
                node_uid=command.node_uid,
                channel=command.channel,
                payload=command_payload,
                now=now,
                stage_name=stage_name,
                planner_step=planner_step,
            )
            if allocated is None:
                return None
            if len(allocated) >= 4:
                ae_command_id, step_no, reused, publish_status = allocated
            elif len(allocated) == 3:
                ae_command_id, step_no, reused = allocated
                publish_status = "pending"
            else:
                ae_command_id, step_no = allocated
                reused = False
                publish_status = "pending"
            if reused:
                COMMAND_CMD_ID_REUSED.labels(stage=stage_name or "unknown").inc()
            cmd_id = build_cmd_id(task_id=int(task.id), zone_id=int(task.zone_id), step_no=int(step_no))
            return int(ae_command_id), int(step_no), cmd_id, bool(reused), str(publish_status or "pending")

        step_no = await self._command_repository.get_next_step_no(task_id=task.id)
        cmd_id = build_cmd_id(task_id=int(task.id), zone_id=int(task.zone_id), step_no=int(step_no))
        stored_payload = dict(command_payload)
        stored_payload["cmd_id"] = cmd_id
        ae_command_id = await self._command_repository.create_pending(
            task_id=task.id,
            step_no=step_no,
            node_uid=command.node_uid,
            channel=command.channel,
            payload=stored_payload,
            now=now,
            stage_name=stage_name,
        )
        if ae_command_id is None:
            return None
        return int(ae_command_id), int(step_no), cmd_id, False, "pending"

    async def publish(
        self,
        *,
        task: Any,
        command: PlannedCommand,
        now: datetime,
        planner_step: str | None = None,
        seq_index: int = 0,
    ) -> CommandPublishResult:
        cmd_name, params = self._extract_publish_payload(command)
        resolved_planner_step = planner_step
        if resolved_planner_step is None:
            resolved_planner_step = planner_step_for_command(task=task, command=command, seq_index=seq_index)

        command_payload = dict(command.payload)
        allocated = await self.allocate_command(
            task=task,
            command=command,
            command_payload=command_payload,
            now=now,
            planner_step=resolved_planner_step,
        )
        if allocated is None:
            raise CommandPublishError(
                f"Задача {task.id} исчезла во время вставки в ae_commands (вероятен конкурентный cleanup)",
            )
        ae_command_id, step_no, cmd_id, cmd_id_reused, publish_status = allocated
        command_payload["cmd_id"] = cmd_id

        prelinked_legacy_id: int | None = None
        skip_hl_publish = cmd_id_reused and publish_status == "accepted"
        if cmd_id_reused and publish_status == "published_unconfirmed":
            prelinked_legacy_id = await self._resolve_legacy_command_id_with_retry(
                zone_id=int(task.zone_id),
                cmd_id=cmd_id,
            )
            skip_hl_publish = prelinked_legacy_id is not None
        published_cmd_id = cmd_id

        try:
            if not skip_hl_publish:
                greenhouse_uid = await self._command_repository.resolve_greenhouse_uid(zone_id=task.zone_id)
                if not greenhouse_uid:
                    raise CommandPublishError(f"Не удалось определить greenhouse_uid для zone_id={task.zone_id}")

                _dispatch_start = time.monotonic()
                published_cmd_id = await self._history_logger_client.publish(
                    greenhouse_uid=greenhouse_uid,
                    zone_id=task.zone_id,
                    node_uid=command.node_uid,
                    channel=command.channel,
                    cmd=cmd_name,
                    params=params,
                    cmd_id=cmd_id,
                )
                COMMAND_DISPATCHED.labels(stage=command.channel or "unknown").inc()
                COMMAND_DISPATCH_DURATION.observe(time.monotonic() - _dispatch_start)
        except Exception as exc:
            normalized_error = str(exc).strip() or type(exc).__name__
            await self._record_publish_error(
                ae_command_id=ae_command_id,
                last_error=normalized_error,
                now=now,
                outcome_unknown=is_publish_outcome_unknown(exc),
            )
            if isinstance(exc, CommandPublishError):
                raise
            raise CommandPublishError(normalized_error) from exc

        mark_unconfirmed = getattr(self._command_repository, "mark_publish_published_unconfirmed", None)
        if callable(mark_unconfirmed) and not skip_hl_publish:
            await mark_unconfirmed(ae_command_id=ae_command_id, now=now)

        legacy_command_id = prelinked_legacy_id
        if legacy_command_id is None:
            legacy_command_id = await self._resolve_legacy_command_id_with_retry(
                zone_id=int(task.zone_id),
                cmd_id=published_cmd_id,
            )
        redriven = False
        external_id: str | None = None
        if legacy_command_id is not None:
            accepted_ok = await self._command_repository.mark_publish_accepted(
                ae_command_id=ae_command_id,
                external_id=str(legacy_command_id),
                now=now,
            )
            if accepted_ok:
                external_id = str(legacy_command_id)
            else:
                redriven = True
                COMMAND_PUBLISH_REDRIVEN.labels(reason="mark_accept_missed").inc()
                logger.warning(
                    "AE3 publish pipeline: mark_publish_accepted missed row task_id=%s ae_command_id=%s cmd_id=%s",
                    task.id,
                    ae_command_id,
                    cmd_id,
                )
        else:
            redriven = True
            COMMAND_PUBLISH_REDRIVEN.labels(reason="legacy_not_found").inc()
            logger.info(
                "AE3 publish pipeline: legacy command not found yet, redrive via reconcile task_id=%s cmd_id=%s",
                task.id,
                published_cmd_id,
            )

        return CommandPublishResult(
            ae_command_id=ae_command_id,
            step_no=step_no,
            cmd_id=cmd_id,
            published_cmd_id=str(published_cmd_id),
            cmd_name=cmd_name,
            params=params,
            external_id=external_id,
            cmd_id_reused=cmd_id_reused,
            redriven=redriven,
        )

    async def redrive_existing(
        self,
        *,
        task: Any,
        ae_command: Mapping[str, Any],
        command: PlannedCommand,
        now: datetime,
    ) -> CommandPublishResult:
        """Повторно публикует уже существующую pending/published_unconfirmed строку без нового INSERT."""
        publish_status = str(ae_command.get("publish_status") or "pending").strip().lower()
        if publish_status not in {"pending", "published_unconfirmed"}:
            raise CommandPublishError(
                f"ae_command {ae_command.get('id')} не eligible для redrive: publish_status={publish_status}",
            )
        payload = ae_command.get("payload") if isinstance(ae_command.get("payload"), Mapping) else {}
        cmd_id = str(payload.get("cmd_id") or "").strip()
        if not cmd_id:
            raise CommandPublishError(f"ae_command {ae_command.get('id')} не содержит payload.cmd_id для redrive")
        try:
            ae_command_id = int(ae_command["id"])
            step_no = int(ae_command.get("step_no") or command.step_no or 1)
        except (TypeError, ValueError, KeyError) as exc:
            raise CommandPublishError(f"Некорректная ae_command строка для redrive: {ae_command.get('id')}") from exc

        cmd_name, params = self._extract_publish_payload(command)
        prelinked_legacy_id: int | None = None
        skip_hl_publish = publish_status == "published_unconfirmed"
        if skip_hl_publish:
            prelinked_legacy_id = await self._resolve_legacy_command_id_with_retry(
                zone_id=int(task.zone_id),
                cmd_id=cmd_id,
            )
            skip_hl_publish = prelinked_legacy_id is not None
        published_cmd_id = cmd_id

        try:
            if not skip_hl_publish:
                greenhouse_uid = await self._command_repository.resolve_greenhouse_uid(zone_id=task.zone_id)
                if not greenhouse_uid:
                    raise CommandPublishError(f"Не удалось определить greenhouse_uid для zone_id={task.zone_id}")

                _dispatch_start = time.monotonic()
                published_cmd_id = await self._history_logger_client.publish(
                    greenhouse_uid=greenhouse_uid,
                    zone_id=task.zone_id,
                    node_uid=command.node_uid,
                    channel=command.channel,
                    cmd=cmd_name,
                    params=params,
                    cmd_id=cmd_id,
                )
                COMMAND_DISPATCHED.labels(stage=command.channel or "unknown").inc()
                COMMAND_DISPATCH_DURATION.observe(time.monotonic() - _dispatch_start)
        except Exception as exc:
            normalized_error = str(exc).strip() or type(exc).__name__
            await self._record_publish_error(
                ae_command_id=ae_command_id,
                last_error=normalized_error,
                now=now,
                outcome_unknown=is_publish_outcome_unknown(exc),
            )
            if isinstance(exc, CommandPublishError):
                raise
            raise CommandPublishError(normalized_error) from exc

        mark_unconfirmed = getattr(self._command_repository, "mark_publish_published_unconfirmed", None)
        if callable(mark_unconfirmed) and not skip_hl_publish:
            await mark_unconfirmed(ae_command_id=ae_command_id, now=now)

        legacy_command_id = prelinked_legacy_id
        if legacy_command_id is None:
            legacy_command_id = await self._resolve_legacy_command_id_with_retry(
                zone_id=int(task.zone_id),
                cmd_id=published_cmd_id,
            )
        external_id: str | None = None
        redriven = True
        if legacy_command_id is not None:
            accepted_ok = await self._command_repository.mark_publish_accepted(
                ae_command_id=ae_command_id,
                external_id=str(legacy_command_id),
                now=now,
            )
            if accepted_ok:
                external_id = str(legacy_command_id)
            else:
                COMMAND_PUBLISH_REDRIVEN.labels(reason="mark_accept_missed").inc()
        else:
            COMMAND_PUBLISH_REDRIVEN.labels(reason="legacy_not_found").inc()

        return CommandPublishResult(
            ae_command_id=ae_command_id,
            step_no=step_no,
            cmd_id=cmd_id,
            published_cmd_id=str(published_cmd_id),
            cmd_name=cmd_name,
            params=params,
            external_id=external_id,
            cmd_id_reused=True,
            redriven=redriven,
        )

    async def _record_publish_error(
        self,
        *,
        ae_command_id: int,
        last_error: str,
        now: datetime,
        outcome_unknown: bool,
    ) -> None:
        """Сохраняет retryable publish error без потери planner_step/cmd_id."""
        try:
            record_retryable = getattr(self._command_repository, "record_publish_retryable_error", None)
            if callable(record_retryable):
                await record_retryable(
                    ae_command_id=ae_command_id,
                    last_error=last_error,
                    now=now,
                    outcome_unknown=outcome_unknown,
                )
                return
            if outcome_unknown:
                mark_unconfirmed = getattr(self._command_repository, "mark_publish_published_unconfirmed", None)
                if callable(mark_unconfirmed):
                    await mark_unconfirmed(ae_command_id=ae_command_id, now=now)
            else:
                logger.debug(
                    "AE3 publish error before HL call; keeping pending ae_command_id=%s error=%s",
                    ae_command_id,
                    last_error,
                )
        except Exception:
            logger.debug(
                "AE3 record_publish_retryable_error skipped ae_command_id=%s",
                ae_command_id,
                exc_info=True,
            )

    async def _resolve_legacy_command_id_with_retry(self, *, zone_id: int, cmd_id: str) -> int | None:
        for attempt in range(_LEGACY_RESOLVE_ATTEMPTS):
            legacy_command_id = await self._command_repository.resolve_legacy_command_id(
                zone_id=zone_id,
                cmd_id=cmd_id,
            )
            if legacy_command_id is not None:
                return int(legacy_command_id)
            if attempt + 1 < _LEGACY_RESOLVE_ATTEMPTS:
                await asyncio.sleep(_LEGACY_RESOLVE_DELAY_SEC)
        return None

    def _extract_publish_payload(self, command: PlannedCommand) -> tuple[str, Mapping[str, Any]]:
        payload = command.payload if isinstance(command.payload, Mapping) else {}
        cmd_name = str(payload.get("cmd") or "").strip()
        params = payload.get("params")
        if not cmd_name or not isinstance(params, Mapping):
            raise CommandPublishError("PlannedCommand должен содержать cmd и params")
        return cmd_name, params


def compute_poll_timeout_sec(
    *,
    params: Mapping[str, Any],
    default_sec: float,
    margin_sec: float,
) -> float:
    duration_ms = params.get("duration_ms")
    if duration_ms is not None:
        try:
            return max(1.0, float(duration_ms) / 1000.0 + float(margin_sec))
        except (TypeError, ValueError):
            pass
    return max(1.0, float(default_sec))
