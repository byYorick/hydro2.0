"""CreateTaskFromIntentUseCase topup: explicit collaborators and invocation context."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Callable, Mapping

from ae3lite.application.level_monitor import load_zone_level_monitor_config, solution_topup_need_active
from ae3lite.domain.errors import TaskCreateError


@dataclass(frozen=True)
class IntentTaskTopupPorts:
    normalize_utc: Callable[..., Any]


class IntentTaskTopup:
    def __init__(self, ports: IntentTaskTopupPorts) -> None:
        self._ports = ports

    async def ensure_solution_topup_preconditions(
        self,
        *,
        zone_id: int,
        meta: Any,
        conn: Any,
        now: datetime,
    ) -> None:
        if str(getattr(meta, "task_type", "") or "").strip().lower() != "solution_topup":
            return

        workflow_row = await conn.fetchrow(
            """
            SELECT workflow_phase
            FROM zone_workflow_state
            WHERE zone_id = $1
            LIMIT 1
            """,
            zone_id,
        )
        workflow_phase = str((workflow_row or {}).get("workflow_phase") or "").strip().lower()
        if workflow_phase != "ready":
            raise TaskCreateError(
                "start_solution_topup_not_ready",
                f"Автодолив доступен только в ready, текущая фаза: {workflow_phase or 'missing'}",
                details={"workflow_phase": workflow_phase or "missing"},
            )

        from ae3lite.infrastructure.read_models.zone_runtime_monitor import PgZoneRuntimeMonitor

        level_cfg = await load_zone_level_monitor_config(zone_id=zone_id, fetch_fn=conn.fetch)
        monitor = PgZoneRuntimeMonitor()
        solution_min = await monitor.read_level_switch(
            zone_id=zone_id,
            sensor_labels=level_cfg["solution_min_sensor_labels"],
            threshold=level_cfg["level_switch_on_threshold"],
            telemetry_max_age_sec=int(level_cfg["telemetry_max_age_sec"]),
        )
        solution_max = await monitor.read_level_switch(
            zone_id=zone_id,
            sensor_labels=level_cfg["solution_max_sensor_labels"],
            threshold=level_cfg["level_switch_on_threshold"],
            telemetry_max_age_sec=int(level_cfg["telemetry_max_age_sec"]),
        )
        if not solution_topup_need_active(
            solution_min_triggered=bool(solution_min.get("is_triggered")),
            solution_max_triggered=bool(solution_max.get("is_triggered")),
        ):
            raise TaskCreateError(
                "start_solution_topup_level_not_low",
                "Нет условия need-topup: требуется solution_min=true и solution_max=false",
                details={
                    "solution_min_triggered": solution_min.get("is_triggered"),
                    "solution_max_triggered": solution_max.get("is_triggered"),
                },
            )

        intent_payload = {}
        intent_meta = getattr(meta, "intent_meta", None)
        if isinstance(intent_meta, Mapping):
            nested = intent_meta.get("intent_payload")
            if isinstance(nested, Mapping):
                intent_payload = dict(nested)
        mode = str(intent_payload.get("mode") or "normal").strip().lower()
        if mode != "force":
            cooldown_sec = 300
            startup_row = await conn.fetchrow(
                """
                SELECT aeb.config
                FROM grow_cycles gc
                JOIN automation_effective_bundles aeb
                  ON aeb.scope_type = 'grow_cycle'
                 AND aeb.scope_id = gc.id
                WHERE gc.zone_id = $1
                  AND gc.status IN ('PLANNED', 'RUNNING', 'PAUSED')
                ORDER BY
                    CASE gc.status
                        WHEN 'RUNNING' THEN 0
                        WHEN 'PAUSED' THEN 1
                        ELSE 2
                    END,
                    gc.id DESC
                LIMIT 1
                """,
                zone_id,
            )
            config = (startup_row or {}).get("config")
            if isinstance(config, Mapping):
                zone_bundle = config.get("zone")
                if isinstance(zone_bundle, Mapping):
                    logic_profile = zone_bundle.get("logic_profile")
                    if isinstance(logic_profile, Mapping):
                        active_profile = logic_profile.get("active_profile")
                        if isinstance(active_profile, Mapping):
                            subsystems = active_profile.get("subsystems")
                            if isinstance(subsystems, Mapping):
                                diagnostics = subsystems.get("diagnostics")
                                if isinstance(diagnostics, Mapping):
                                    execution = diagnostics.get("execution")
                                    if isinstance(execution, Mapping):
                                        startup = execution.get("startup")
                                        if (
                                            isinstance(startup, Mapping)
                                            and startup.get("solution_topup_cooldown_sec") is not None
                                        ):
                                            try:
                                                cooldown_sec = max(0, int(startup.get("solution_topup_cooldown_sec")))
                                            except (TypeError, ValueError):
                                                pass
            recent = await conn.fetchrow(
                """
                SELECT created_at
                FROM zone_events
                WHERE zone_id = $1
                  AND type IN (
                        'SOLUTION_TOPUP_DONE',
                        'SOLUTION_TOPUP_TIMEOUT',
                        'SOLUTION_TOPUP_SOURCE_EMPTY',
                        'SOLUTION_TOPUP_LEAK_DETECTED'
                  )
                ORDER BY created_at DESC
                LIMIT 1
                """,
                zone_id,
            )
            if recent and cooldown_sec > 0:
                created_at = recent.get("created_at")
                if isinstance(created_at, datetime):
                    anchor = created_at.replace(tzinfo=None) if created_at.tzinfo else created_at
                    now_naive = self._ports.normalize_utc(now)
                    if anchor + timedelta(seconds=cooldown_sec) > now_naive:
                        raise TaskCreateError(
                            "start_solution_topup_cooldown_active",
                            "Cooldown после предыдущего solution_topup ещё не истёк",
                            details={"cooldown_sec": cooldown_sec},
                        )
