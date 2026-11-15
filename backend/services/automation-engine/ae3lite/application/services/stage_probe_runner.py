"""Stage component: probe core. Explicit ports; no handler dependency."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime
from time import monotonic
from typing import Any, Awaitable, Callable, Mapping, Sequence

from ae3lite.config.schema import RuntimePlan
from ae3lite.domain.errors import TaskExecutionError

_logger = logging.getLogger("ae3lite.application.handlers.base")


@dataclass(frozen=True)
class StageProbeRunnerPorts:
    irr_probe_node_unreachable_heartbeat_age_sec: Callable[[], Any]
    irr_state_probe_retry_count: Callable[[], Any]
    irr_state_probe_retry_delay_sec: Callable[[], Any]
    log_probe_failure_event: Callable[..., Awaitable[Any]]
    maybe_emit_node_reboot_event: Callable[..., Awaitable[Any]]
    raise_execution_error: Callable[..., Awaitable[Any]]
    remember_probe_state: Callable[..., Any]
    require_runtime_plan: Callable[..., Any]
    run_command_batch_checked: Callable[..., Awaitable[Any]]
    runtime_config: Callable[[], Any]
    runtime_monitor: Callable[[], Any]


class StageProbeRunner:
    def __init__(self, ports: StageProbeRunnerPorts) -> None:
        self._ports = ports

    async def probe_irr_state(
        self,
        *,
        task: Any,
        plan: Any,
        now: datetime,
        expected: Mapping[str, bool],
    ) -> None:
        """Отправляет probe-команду и проверяет, что состояние hardware совпадает с ожиданиями."""
        await self.ensure_irr_probe_node_online(task=task, plan=plan)
        probe_cmds = plan.named_plans.get("irr_state_probe", ())
        if not probe_cmds:
            raise TaskExecutionError(
                "irr_state_probe_plan_missing",
                f"Для stage={getattr(task, 'current_stage', None)} отсутствует command plan зонда IRR state",
            )
        runtime = self._ports.require_runtime_plan(plan=plan)
        last_state: Mapping[str, Any] = {}
        last_probe_cmd_id: str | None = None
        total_attempts = 1 + self._ports.irr_state_probe_retry_count()

        for attempt_index in range(total_attempts):
            result = await self._ports.run_command_batch_checked(
                task=task,
                commands=probe_cmds,
                now=now,
                track_task_state=False,
            )
            probe_cmd_id = self.extract_probe_cmd_id(result=result)
            state = await self.read_probe_state_with_retry(
                task=task,
                runtime=runtime,
                expected=expected,
                expected_cmd_id=probe_cmd_id,
            )
            last_state = state
            last_probe_cmd_id = probe_cmd_id
            if not self.probe_state_needs_retry(
                state=state,
                expected=expected,
                expected_cmd_id=probe_cmd_id,
            ):
                self._ports.remember_probe_state(task=task, state=state)
                return
            if attempt_index + 1 < total_attempts:
                await asyncio.sleep(self._ports.irr_state_probe_retry_delay_sec())

        reason = self.classify_probe_failure_reason(
            state=last_state,
            expected=expected,
            expected_cmd_id=last_probe_cmd_id,
        )
        await self._ports.log_probe_failure_event(
            task=task,
            expected=expected,
            expected_cmd_id=last_probe_cmd_id,
            state=last_state,
            reason=reason,
        )
        if reason == "stale":
            raise TaskExecutionError(
                "irr_state_stale",
                "Снимок состояния IRR-ноды устарел",
            )
        if reason == "mismatch":
            snapshot = last_state["snapshot"] if isinstance(last_state["snapshot"], Mapping) else {}
            if self.is_solution_fill_terminal_snapshot(task=task, expected=expected, snapshot=snapshot):
                # Для test-node допустим штатный terminal snapshot на solution_fill_check:
                # путь already closed после достижения solution_level_max.
                self._ports.remember_probe_state(task=task, state=last_state)
                return
            await self._ports.maybe_emit_node_reboot_event(
                task=task,
                plan=plan,
                expected=expected,
                snapshot=snapshot,
            )
            for key, value in expected.items():
                if bool(snapshot.get(key)) != bool(value):
                    raise TaskExecutionError(
                        "irr_state_mismatch",
                        f"Состояние IRR-ноды не совпало по признаку {key}: ожидалось={value}, получено={snapshot.get(key)}",
                    )
        if await self.irr_probe_node_is_offline(task=task, plan=plan):
            failure = await self.offline_failure_for_irr_probe(task=task, plan=plan)
            raise TaskExecutionError(failure.code, failure.message)
        await self._ports.raise_execution_error(
            task=task,
            error_code="irr_state_unavailable",
            error_message="Снимок состояния IRR-ноды недоступен",
            node_uid=self.extract_irr_probe_node_uid(plan=plan),
            plan=plan,
        )

    async def ensure_irr_probe_node_online(self, *, task: Any, plan: Any) -> None:
        if not await self.irr_probe_node_is_offline(task=task, plan=plan):
            return
        failure = await self.offline_failure_for_irr_probe(task=task, plan=plan)
        raise TaskExecutionError(failure.code, failure.message)

    async def irr_probe_node_is_offline(self, *, task: Any, plan: Any) -> bool:
        node_uid = self.extract_irr_probe_node_uid(plan=plan)
        if not node_uid:
            return False
        read_node_liveness = getattr(self._ports.runtime_monitor(), "read_node_liveness", None)
        if not callable(read_node_liveness):
            return False
        from ae3lite.domain.services.zone_node_availability import liveness_is_unreachable

        liveness = await read_node_liveness(node_uid=node_uid)
        return liveness_is_unreachable(
            liveness,
            heartbeat_age_limit_sec=self._ports.irr_probe_node_unreachable_heartbeat_age_sec(),
        )

    async def offline_failure_for_irr_probe(self, *, task: Any, plan: Any) -> Any:
        from ae3lite.domain.services.zone_node_availability import offline_failure_from_liveness

        node_uid = self.extract_irr_probe_node_uid(plan=plan) or ""
        liveness: Mapping[str, Any] = {}
        read_node_liveness = getattr(self._ports.runtime_monitor(), "read_node_liveness", None)
        if node_uid and callable(read_node_liveness):
            raw = await read_node_liveness(node_uid=node_uid)
            if isinstance(raw, Mapping):
                liveness = raw
        return offline_failure_from_liveness(
            zone_id=int(getattr(task, "zone_id", 0) or 0),
            node_uid=node_uid,
            liveness=liveness,
        )

    @staticmethod
    def is_solution_fill_terminal_snapshot(
        *,
        task: Any,
        expected: Mapping[str, bool],
        snapshot: Mapping[str, Any],
    ) -> bool:
        stage = str(getattr(task, "current_stage", "") or "").strip().lower()
        if stage != "solution_fill_check":
            return False
        if not isinstance(snapshot, Mapping):
            return False

        # Для solution_fill terminal-condition в test-node приходит как:
        # solution_level_max=true и flow-path уже выключен.
        if not bool(snapshot.get("solution_level_max")):
            return False

        truthy_expected_keys = [key for key, value in expected.items() if bool(value)]
        if not truthy_expected_keys:
            return False
        return all(not bool(snapshot.get(key)) for key in truthy_expected_keys)

    def extract_irr_probe_node_uid(self, *, plan: Any) -> str | None:
        named_plans = getattr(plan, "named_plans", None) if plan is not None else None
        if not isinstance(named_plans, Mapping):
            return None
        probe_cmds = named_plans.get("irr_state_probe", ())
        for cmd in probe_cmds or ():
            uid = str(getattr(cmd, "node_uid", "") or "").strip()
            if uid:
                return uid
        return None

    def classify_probe_failure_reason(
        self,
        *,
        state: Mapping[str, Any],
        expected: Mapping[str, bool],
        expected_cmd_id: str | None = None,
    ) -> str:
        if not state.get("has_snapshot"):
            return "unavailable"
        if state.get("is_stale"):
            return "stale"
        if expected_cmd_id is not None and str(state.get("cmd_id") or "").strip() != expected_cmd_id:
            return "cmd_id_mismatch"
        snapshot = state.get("snapshot")
        if not isinstance(snapshot, Mapping):
            return "unavailable"
        for key, value in expected.items():
            if bool(snapshot.get(key)) != bool(value):
                return "mismatch"
        return "unavailable"

    async def read_probe_state_with_retry(
        self,
        *,
        task: Any,
        runtime: RuntimePlan,
        expected: Mapping[str, bool],
        expected_cmd_id: str | None = None,
    ) -> Mapping[str, Any]:
        max_age_sec = int(runtime.irr_state_max_age_sec)
        wait_timeout = self._ports.runtime_config().coerce_float(runtime.irr_state_wait_timeout_sec)
        poll_interval = self._ports.runtime_config().coerce_float(
            getattr(runtime, "irr_state_wait_poll_interval_sec", None)
        )
        timeout_sec = max(
            0.0, wait_timeout if wait_timeout is not None else 5.0
        )  # config-literal: fallback probe wait budget
        interval_sec = max(0.05, poll_interval if poll_interval is not None else 0.5)

        state = await self._ports.runtime_monitor().read_latest_irr_state(
            zone_id=task.zone_id,
            max_age_sec=max_age_sec,
            expected_cmd_id=expected_cmd_id,
        )
        if (
            not self.probe_state_needs_retry(
                state=state,
                expected=expected,
                expected_cmd_id=expected_cmd_id,
            )
            or timeout_sec <= 0.0
        ):
            return state

        deadline = monotonic() + timeout_sec
        while monotonic() < deadline:
            await asyncio.sleep(min(interval_sec, max(0.0, deadline - monotonic())))
            state = await self._ports.runtime_monitor().read_latest_irr_state(
                zone_id=task.zone_id,
                max_age_sec=max_age_sec,
                expected_cmd_id=expected_cmd_id,
            )
            if not self.probe_state_needs_retry(
                state=state,
                expected=expected,
                expected_cmd_id=expected_cmd_id,
            ):
                return state
        return state

    def probe_state_needs_retry(
        self,
        *,
        state: Mapping[str, Any],
        expected: Mapping[str, bool],
        expected_cmd_id: str | None = None,
    ) -> bool:
        if not state.get("has_snapshot") or state.get("is_stale"):
            return True
        if expected_cmd_id is not None and str(state.get("cmd_id") or "").strip() != expected_cmd_id:
            return True
        snapshot = state.get("snapshot")
        if not isinstance(snapshot, Mapping):
            return True
        for key, value in expected.items():
            if bool(snapshot.get(key)) != bool(value):
                return True
        return False

    def extract_probe_cmd_id(self, *, result: Mapping[str, Any]) -> str | None:
        statuses = result.get("command_statuses")
        if not isinstance(statuses, Sequence):
            return None
        for item in reversed(statuses):
            if not isinstance(item, Mapping):
                continue
            probe_cmd_id = str(item.get("legacy_cmd_id") or "").strip()
            if probe_cmd_id:
                return probe_cmd_id
        return None
