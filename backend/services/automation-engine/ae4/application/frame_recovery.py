"""Подъём незакрытого кадра после рестарта воркера AE4."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional

from ae4.application.safety_stop import close_irrigation_tract
from ae4.config.zone_plan import ZonePlanConfigurationError, load_zone_plan
from ae4.domain.entities import Ae4Task
from ae4.infrastructure.failure_report import report_failure
from ae4.infrastructure.repositories.ae_command_repository import PgAeCommandRepository
from ae4.infrastructure.repositories.automation_task_repository import (
    PgAutomationTaskRepository,
)
from common.history_logger_gateway import HistoryLoggerGateway

logger = logging.getLogger(__name__)


async def recover_inflight_tasks(
    *,
    task_repository: PgAutomationTaskRepository,
    command_repository: PgAeCommandRepository,
    gateway: HistoryLoggerGateway,
    worker_owner: str,
    now: datetime,
) -> int:
    """Досылает irrigation_stop для незакрытого кадра; второй кадр не открывает.

    Чужой runtime (ae3) не подхватывается.
    """
    tasks = await task_repository.list_inflight_for_ae4(worker_owner=worker_owner)
    recovered = 0
    for task in tasks:
        did = await recover_task_open_frame(
            task=task,
            task_repository=task_repository,
            command_repository=command_repository,
            gateway=gateway,
            worker_owner=worker_owner,
            now=now,
        )
        if did:
            recovered += 1
    return recovered


async def recover_task_open_frame(
    *,
    task: Ae4Task,
    task_repository: PgAutomationTaskRepository,
    command_repository: PgAeCommandRepository,
    gateway: HistoryLoggerGateway,
    worker_owner: str,
    now: datetime,
) -> bool:
    open_starts = await command_repository.list_open_irrigation_starts(task_id=task.id)
    if not open_starts:
        return False

    logger.warning(
        "AE4: незакрытый кадр после рестарта, досылаем irrigation_stop",
        extra={"zone_id": task.zone_id, "task_id": task.id},
    )
    try:
        plan = await load_zone_plan(zone_id=task.zone_id)
        step_no = await command_repository.get_next_step_no(task_id=task.id)
        await close_irrigation_tract(
            plan=plan,
            gateway=gateway,
            task_id=task.id,
            zone_id=task.zone_id,
            now=now,
            step_base=step_no,
            node_uid_by_channel=_node_uid_hint(open_starts),
        )
        await task_repository.mark_failed(
            task_id=task.id,
            owner=worker_owner,
            error_code="ae4_open_frame_recovered",
            error_message="Незакрытый кадр закрыт после рестарта",
            now=now,
        )
        await report_failure(
            zone_id=task.zone_id,
            reason_code="ae4_open_frame_recovered",
            human_message="Незакрытый кадр полива закрыт после рестарта",
            task_id=task.id,
            error_code="ae4_open_frame_recovered",
        )
        return True
    except ZonePlanConfigurationError as exc:
        await report_failure(
            zone_id=task.zone_id,
            reason_code=exc.reason_code,
            human_message=str(exc),
            task_id=task.id,
            error_code=exc.reason_code,
        )
        await task_repository.mark_failed(
            task_id=task.id,
            owner=worker_owner,
            error_code=exc.reason_code,
            error_message=str(exc),
            now=now,
        )
        return True
    except Exception as exc:
        await report_failure(
            zone_id=task.zone_id,
            reason_code="ae4_frame_recovery_failed",
            human_message=f"Не удалось закрыть кадр после рестарта: {exc}",
            task_id=task.id,
            error_code="ae4_frame_recovery_failed",
            details={"exception_type": type(exc).__name__},
        )
        await task_repository.mark_failed(
            task_id=task.id,
            owner=worker_owner,
            error_code="ae4_frame_recovery_failed",
            error_message=str(exc),
            now=now,
        )
        return True


async def fail_stale_inflight_tasks(
    *,
    task_repository: PgAutomationTaskRepository,
    worker_owner: str,
    now: datetime,
    max_age_sec: float,
) -> int:
    """Закрывает in-flight задачи без движения дольше max_age_sec."""
    tasks = await task_repository.list_inflight_for_ae4(worker_owner=worker_owner)
    now_naive = _as_utc_naive(now)
    failed = 0
    for task in tasks:
        age_sec = (now_naive - _as_utc_naive(task.updated_at)).total_seconds()
        if age_sec < float(max_age_sec):
            continue
        await report_failure(
            zone_id=task.zone_id,
            reason_code="ae4_task_stale",
            human_message=(
                f"Задача {task.id} без движения {int(age_sec)} с — закрыта, чтобы не висеть"
            ),
            task_id=task.id,
            error_code="ae4_task_stale",
        )
        await task_repository.mark_failed(
            task_id=task.id,
            owner=worker_owner,
            error_code="ae4_task_stale",
            error_message=f"stale inflight age_sec={int(age_sec)}",
            now=now,
        )
        failed += 1
    return failed


def _as_utc_naive(value: datetime) -> datetime:
    if value.tzinfo is not None:
        value = value.astimezone(timezone.utc).replace(tzinfo=None)
    return value.replace(microsecond=0)


def _node_uid_hint(open_starts: list[dict[str, Any]]) -> dict[str, str]:
    hint: dict[str, str] = {}
    for row in open_starts:
        channel = str(row.get("channel") or "").strip()
        node_uid = str(row.get("node_uid") or "").strip()
        if channel and node_uid:
            hint[channel] = node_uid
    return hint


__all__ = [
    "fail_stale_inflight_tasks",
    "recover_inflight_tasks",
    "recover_task_open_frame",
]
