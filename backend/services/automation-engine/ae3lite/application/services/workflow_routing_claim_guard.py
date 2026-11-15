"""WorkflowRouter claim guard: explicit collaborators and invocation context."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from ae3lite.application.services.workflow_routing_shared import logger
from ae3lite.domain.claim_fence import claim_generation, claim_owner
from ae3lite.domain.errors import TaskExecutionError


@dataclass(frozen=True)
class WorkflowRoutingClaimGuardPorts:
    task_repo: Callable[[], Any]


class WorkflowRoutingClaimGuard:
    def __init__(self, ports: WorkflowRoutingClaimGuardPorts) -> None:
        self._ports = ports

    async def require_original_claim(self, *, task: Any) -> tuple[str, int]:
        """Возвращает token исходного claim. Чужой owner или generation — отказ писать.

        Пустой claimed_by в БД (уже pending после своего requeue) не подменяется
        чужим именем: SQL CAS дальше не запишет outcome в чужой claim.
        """
        owner = claim_owner(task)
        generation = claim_generation(task)
        if not owner:
            raise TaskExecutionError(
                "ae3_stale_claim_rejected",
                f"У задачи {getattr(task, 'id', None)} нет claimed_by для записи outcome",
            )
        get_task_by_id = getattr(self._ports.task_repo(), "get_by_id", None)
        if not callable(get_task_by_id):
            return owner, generation
        try:
            fresh = await get_task_by_id(task_id=int(task.id))
        except Exception:
            logger.warning(
                "AE3 не смог перечитать claim token перед записью task_id=%s",
                getattr(task, "id", None),
                exc_info=True,
            )
            return owner, generation
        if fresh is None:
            return owner, generation
        fresh_owner = claim_owner(fresh)
        fresh_generation = claim_generation(fresh)
        if fresh_owner and (fresh_owner != owner or fresh_generation != generation):
            logger.info(
                "AE3 stale claim rejected: task_id=%s owner=%s generation=%s fresh_owner=%s fresh_generation=%s",
                getattr(task, "id", None),
                owner,
                generation,
                fresh_owner,
                fresh_generation,
            )
            raise TaskExecutionError(
                "ae3_stale_claim_rejected",
                "Смена владельца или поколения claim запрещает запись outcome",
            )
        return owner, generation

    async def resolve_inactive_terminal_task(
        self,
        *,
        task_id: int,
        updated_task: Any,
        error_code: str,
        error_message: str,
        expected_stage: str | None = None,
        expected_corr_step: str | None = None,
    ) -> Any:
        if updated_task is not None:
            return updated_task
        get_task_by_id = getattr(self._ports.task_repo(), "get_by_id", None)
        if callable(get_task_by_id):
            current_task = await get_task_by_id(task_id=task_id)
            if current_task is not None:
                if not bool(getattr(current_task, "is_active", False)):
                    return current_task
                status = str(getattr(current_task, "status", "") or "").strip().lower()
                if expected_stage is not None:
                    current_stage = str(getattr(current_task, "current_stage", "") or "").strip()
                    if current_stage == expected_stage and status == "pending":
                        logger.info(
                            "AE3 stage apply idempotent: task_id=%s already pending at stage=%s",
                            task_id,
                            expected_stage,
                        )
                        return current_task
                if expected_corr_step is not None:
                    current_corr = getattr(current_task, "correction", None)
                    current_corr_step = str(getattr(current_corr, "corr_step", "") or "").strip()
                    if current_corr_step == expected_corr_step and status == "pending":
                        logger.info(
                            "AE3 correction apply idempotent: task_id=%s already pending with corr_step=%s",
                            task_id,
                            expected_corr_step,
                        )
                        return current_task
        raise TaskExecutionError(error_code, error_message)
