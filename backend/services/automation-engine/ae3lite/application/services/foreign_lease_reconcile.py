"""Эскалация reconcile/recovery при чужом активном zone lease (H6)."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone as _tz
from enum import Enum
from typing import Any

from ae3lite.application.services.task_failed_alert import emit_task_failed_alert
from ae3lite.domain.entities import AutomationTask
from ae3lite.domain.errors import ErrorCodes
from ae3lite.infrastructure.metrics import RECONCILE_FOREIGN_LEASE
from common.infra_alerts import send_infra_alert

logger = logging.getLogger(__name__)


class ForeignLeaseAction(str, Enum):
    """Решение reconcile/recovery при чужом активном lease."""

    ALLOW = "allow"
    SKIP = "skip"
    ESCALATE = "escalate"


@dataclass(frozen=True)
class ForeignLeaseContext:
    """Снимок чужого lease, блокирующего reconcile."""

    lease_owner: str
    leased_until: datetime | None


def default_foreign_lease_escalate_sec(*, lease_ttl_sec: int, stale_claimed_ttl_sec: int) -> int:
    """Дефолтный порог эскалации: max(lease_ttl*2, stale_claimed_ttl, 240s)."""
    return max(int(lease_ttl_sec) * 2, int(stale_claimed_ttl_sec), 240)


def task_reconcile_age_sec(*, task: AutomationTask, now: datetime) -> float:
    """Возраст задачи для foreign-lease эскалации (claimed_at или updated_at)."""
    normalized_now = (
        now.astimezone(_tz.utc).replace(tzinfo=None)
        if now.tzinfo is not None
        else now.replace(microsecond=0)
    )
    if str(task.status or "").strip().lower() == "claimed" and task.claimed_at is not None:
        anchor = task.claimed_at
    else:
        anchor = task.updated_at
    if anchor is None:
        return 0.0
    anchor_naive = (
        anchor.astimezone(_tz.utc).replace(tzinfo=None)
        if getattr(anchor, "tzinfo", None) is not None
        else anchor
    )
    return max(0.0, (normalized_now - anchor_naive).total_seconds())


async def get_foreign_lease_context(
    *,
    lease_repository: Any,
    zone_id: int,
    worker_owner: str,
    now: datetime,
) -> ForeignLeaseContext | None:
    """Возвращает контекст чужого активного lease или None, если reconcile не блокируется."""
    normalized_worker = str(worker_owner or "").strip()
    if not normalized_worker:
        return None

    get_lease = getattr(lease_repository, "get", None)
    if not callable(get_lease):
        return None

    lease = await get_lease(zone_id=zone_id)
    if lease is None:
        return None

    lease_owner = str(getattr(lease, "owner", "") or "").strip()
    if lease_owner == "" or lease_owner == normalized_worker:
        return None

    leased_until = getattr(lease, "leased_until", None)
    if leased_until is not None:
        normalized_now = (
            now.astimezone(_tz.utc).replace(tzinfo=None)
            if now.tzinfo is not None
            else now.replace(microsecond=0)
        )
        lease_until = (
            leased_until.astimezone(_tz.utc).replace(tzinfo=None)
            if getattr(leased_until, "tzinfo", None) is not None
            else leased_until
        )
        if lease_until <= normalized_now:
            return None

    return ForeignLeaseContext(lease_owner=lease_owner, leased_until=leased_until)


async def resolve_foreign_active_lease(
    *,
    lease_repository: Any,
    zone_id: int,
    worker_owner: str,
    task: AutomationTask,
    now: datetime,
    escalate_sec: int,
) -> tuple[ForeignLeaseAction, ForeignLeaseContext | None]:
    """Определяет allow/skip/escalate для задачи, заблокированной чужим lease."""
    lease_context = await get_foreign_lease_context(
        lease_repository=lease_repository,
        zone_id=zone_id,
        worker_owner=worker_owner,
        now=now,
    )
    if lease_context is None:
        return ForeignLeaseAction.ALLOW, None

    age_sec = task_reconcile_age_sec(task=task, now=now)
    threshold = max(1, int(escalate_sec))
    if age_sec >= threshold:
        return ForeignLeaseAction.ESCALATE, lease_context
    return ForeignLeaseAction.SKIP, lease_context


async def escalate_foreign_lease_stale_task(
    *,
    task_repository: Any,
    alert_repository: Any | None,
    task: AutomationTask,
    now: datetime,
    recovery_source: str,
    lease_context: ForeignLeaseContext | None = None,
) -> AutomationTask | None:
    """Fail-closed эскалация: fail task + biz/infra alert, без release чужого lease."""
    error_code = ErrorCodes.AE3_FOREIGN_LEASE_STALE
    lease_owner = str(lease_context.lease_owner if lease_context else "").strip() or "unknown"
    task_id = int(task.id)
    zone_id = int(task.zone_id)
    age_sec = round(task_reconcile_age_sec(task=task, now=now), 3)
    error_message = (
        f"Задача {task_id} заблокирована чужим zone lease ({lease_owner}) "
        f"дольше порога эскалации (age_sec={age_sec})"
    )

    fail_for_recovery = getattr(task_repository, "fail_for_recovery", None)
    if not callable(fail_for_recovery):
        logger.warning(
            "Foreign lease escalate: fail_for_recovery unavailable task_id=%s zone_id=%s source=%s",
            task_id,
            zone_id,
            recovery_source,
        )
        return None

    failed = await fail_for_recovery(
        task_id=task_id,
        error_code=error_code,
        error_message=error_message,
        now=now,
    )
    if failed is None:
        logger.warning(
            "Foreign lease escalate: fail_for_recovery noop task_id=%s zone_id=%s source=%s",
            task_id,
            zone_id,
            recovery_source,
        )
        return None

    source = str(recovery_source or "").strip() or "unknown"
    RECONCILE_FOREIGN_LEASE.labels(source=source, outcome="escalated").inc()

    extra_details = {
        "recovery_source": source,
        "foreign_lease_owner": lease_owner,
        "task_age_sec": age_sec,
    }
    if lease_context is not None and lease_context.leased_until is not None:
        leased_until = lease_context.leased_until
        extra_details["foreign_lease_until"] = (
            leased_until.astimezone(_tz.utc).isoformat()
            if getattr(leased_until, "tzinfo", None) is not None
            else leased_until.isoformat()
        )

    await emit_task_failed_alert(
        alert_repository=alert_repository,
        task=failed,
        error_code=error_code,
        error_message=str(failed.error_message or error_message),
        now=now,
        extra_details=extra_details,
    )

    try:
        await send_infra_alert(
            code=error_code,
            alert_type="AE3 Foreign Lease Stale",
            message=(
                "Reconcile/recovery пропускал задачу из-за чужого активного zone lease "
                "дольше порога эскалации; задача переведена в failed без release lease."
            ),
            severity="error",
            zone_id=zone_id,
            service="automation-engine",
            component=source,
            details={
                "task_id": task_id,
                "foreign_lease_owner": lease_owner,
                "task_age_sec": age_sec,
                "recovery_source": source,
                "message": error_message,
            },
        )
    except Exception:
        logger.warning(
            "Foreign lease escalate: infra alert failed task_id=%s zone_id=%s source=%s",
            task_id,
            zone_id,
            recovery_source,
            exc_info=True,
        )

    logger.warning(
        "Foreign lease escalate: task failed task_id=%s zone_id=%s lease_owner=%s age_sec=%s source=%s",
        task_id,
        zone_id,
        lease_owner,
        age_sec,
        source,
    )
    return failed


def record_foreign_lease_skip(*, recovery_source: str) -> None:
    """Инкрементирует метрику skip при bounded defer эскалации."""
    source = str(recovery_source or "").strip() or "unknown"
    RECONCILE_FOREIGN_LEASE.labels(source=source, outcome="skipped").inc()
