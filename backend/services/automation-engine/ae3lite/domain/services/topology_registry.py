"""Topology registry: static stage graph for workflow routing.

Each topology (e.g. ``two_tank_drip_substrate_trays``) is a mapping from
stage name to :class:`StageDef`.  The :class:`TopologyRegistry` provides
lookup by ``(topology, stage_name)`` and graph-integrity validation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping, Optional, Tuple


# ---------------------------------------------------------------------------
# StageDef
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class StageDef:
    """Declarative definition of a single stage in a workflow topology.

    Attributes:
        name: Unique stage identifier (e.g. ``"clean_fill_start"``).
        handler: Handler class key used by :class:`WorkflowRouter` for dispatch
            (``"command"``, ``"startup"``, ``"clean_fill"``, ``"solution_fill"``,
            ``"prepare_recirc"``, ``"ready"``).
        workflow_phase: Zone-level phase reported to external observers.
        command_plans: Tuple of named plan keys executed by ``CommandHandler``.
        next_stage: Static successor stage after successful command execution.
        terminal_error: ``(error_code, error_message)`` — if set the command
            stage is a terminal failure stage.
        timeout_key: Runtime config key whose value (seconds) is used to
            compute ``stage_deadline_at`` when entering this stage.
        has_correction: Whether this check stage can initiate a correction cycle.
        on_corr_success: Stage to transition to when correction succeeds.
        on_corr_fail: Stage to transition to when correction fails.
    """

    name: str
    handler: str
    workflow_phase: str = "idle"

    # Command stages
    command_plans: Tuple[str, ...] = ()
    next_stage: Optional[str] = None

    # Terminal failure
    terminal_error: Optional[Tuple[str, str]] = None

    # Check stages
    timeout_key: Optional[str] = None
    has_correction: bool = False
    on_corr_success: Optional[str] = None
    on_corr_fail: Optional[str] = None


# ---------------------------------------------------------------------------
# Two-tank drip substrate trays topology (full graph)
# ---------------------------------------------------------------------------

TWO_TANK: Mapping[str, StageDef] = {
    # === Startup ===
    "startup": StageDef("startup", "startup"),

    # === Clean fill path ===
    "clean_fill_start": StageDef(
        "clean_fill_start", "command",
        workflow_phase="tank_filling",
        command_plans=("clean_fill_start",),
        next_stage="clean_fill_check",
    ),
    "clean_fill_check": StageDef(
        "clean_fill_check", "clean_fill",
        workflow_phase="tank_filling",
        timeout_key="clean_fill_timeout_sec",
    ),
    "clean_fill_stop_to_solution": StageDef(
        "clean_fill_stop_to_solution", "command",
        workflow_phase="tank_filling",
        command_plans=("clean_fill_stop",),
        next_stage="solution_fill_start",
    ),
    "clean_fill_retry_stop": StageDef(
        "clean_fill_retry_stop", "command",
        workflow_phase="tank_filling",
        command_plans=("clean_fill_stop",),
        next_stage="clean_fill_start",
    ),
    "clean_fill_timeout_stop": StageDef(
        "clean_fill_timeout_stop", "command",
        workflow_phase="tank_filling",
        command_plans=("clean_fill_stop",),
        terminal_error=(
            "clean_tank_not_filled_timeout",
            "Clean fill timeout exceeded",
        ),
    ),

    # === Solution fill path ===
    "solution_fill_start": StageDef(
        "solution_fill_start", "command",
        workflow_phase="tank_filling",
        command_plans=("sensor_mode_activate", "solution_fill_start"),
        next_stage="solution_fill_check",
    ),
    "solution_fill_check": StageDef(
        "solution_fill_check", "solution_fill",
        workflow_phase="tank_filling",
        timeout_key="solution_fill_timeout_sec",
        has_correction=True,
        on_corr_success="solution_fill_check",
        on_corr_fail="solution_fill_check",
    ),
    "solution_fill_stop_to_ready": StageDef(
        "solution_fill_stop_to_ready", "command",
        workflow_phase="ready",
        command_plans=("solution_fill_stop", "sensor_mode_deactivate"),
        next_stage="complete_ready",
    ),
    "solution_fill_stop_to_prepare": StageDef(
        "solution_fill_stop_to_prepare", "command",
        workflow_phase="tank_recirc",
        command_plans=("solution_fill_stop", "sensor_mode_deactivate"),
        next_stage="prepare_recirculation_start",
    ),
    "solution_fill_timeout_stop": StageDef(
        "solution_fill_timeout_stop", "command",
        workflow_phase="tank_filling",
        command_plans=("solution_fill_stop", "sensor_mode_deactivate"),
        terminal_error=(
            "solution_tank_not_filled_timeout",
            "Solution fill timeout exceeded",
        ),
    ),

    # === Prepare recirculation path ===
    "prepare_recirculation_start": StageDef(
        "prepare_recirculation_start", "command",
        workflow_phase="tank_recirc",
        command_plans=("sensor_mode_activate", "prepare_recirculation_start"),
        next_stage="prepare_recirculation_check",
    ),
    "prepare_recirculation_check": StageDef(
        "prepare_recirculation_check", "prepare_recirc",
        workflow_phase="tank_recirc",
        timeout_key="prepare_recirculation_timeout_sec",
        has_correction=True,
        on_corr_success="prepare_recirculation_stop_to_ready",
        on_corr_fail="prepare_recirculation_window_exhausted",
    ),
    "prepare_recirculation_window_exhausted": StageDef(
        "prepare_recirculation_window_exhausted", "prepare_recirc_window",
        workflow_phase="tank_recirc",
    ),
    "prepare_recirculation_stop_to_ready": StageDef(
        "prepare_recirculation_stop_to_ready", "command",
        workflow_phase="ready",
        command_plans=("prepare_recirculation_stop", "sensor_mode_deactivate"),
        next_stage="complete_ready",
    ),
    # === Irrigation path ===
    "await_ready": StageDef("await_ready", "await_ready", workflow_phase="ready"),
    "decision_gate": StageDef("decision_gate", "decision_gate", workflow_phase="ready"),
    "irrigation_start": StageDef(
        "irrigation_start", "command",
        workflow_phase="irrigating",
        command_plans=("sensor_mode_activate", "irrigation_start"),
        next_stage="irrigation_check",
    ),
    "irrigation_check": StageDef(
        "irrigation_check", "irrigation_check",
        workflow_phase="irrigating",
    ),
    "irrigation_stop_to_ready": StageDef(
        "irrigation_stop_to_ready", "command",
        workflow_phase="ready",
        command_plans=("irrigation_stop", "sensor_mode_deactivate"),
        next_stage="completed_run",
    ),
    "irrigation_stop_to_recovery": StageDef(
        "irrigation_stop_to_recovery", "command",
        workflow_phase="irrig_recirc",
        command_plans=("irrigation_stop", "sensor_mode_deactivate"),
        next_stage="irrigation_recovery_start",
    ),
    "irrigation_stop_to_setup": StageDef(
        "irrigation_stop_to_setup", "command",
        workflow_phase="tank_filling",
        command_plans=("irrigation_stop", "sensor_mode_deactivate"),
        next_stage="startup",
    ),
    "irrigation_recovery_start": StageDef(
        "irrigation_recovery_start", "command",
        workflow_phase="irrig_recirc",
        command_plans=("sensor_mode_activate", "irrigation_recovery_start"),
        next_stage="irrigation_recovery_check",
    ),
    "irrigation_recovery_check": StageDef(
        "irrigation_recovery_check", "irrigation_recovery",
        workflow_phase="irrig_recirc",
        timeout_key="prepare_recirculation_timeout_sec",
        has_correction=True,
        on_corr_success="irrigation_recovery_stop_to_ready",
        on_corr_fail="irrigation_recovery_stop_to_ready",
    ),
    "irrigation_recovery_stop_to_ready": StageDef(
        "irrigation_recovery_stop_to_ready", "command",
        workflow_phase="ready",
        command_plans=("irrigation_recovery_stop", "sensor_mode_deactivate"),
        next_stage="completed_run",
    ),
    # === Terminal ===
    "complete_ready": StageDef("complete_ready", "ready", workflow_phase="ready"),
    "completed_run": StageDef("completed_run", "ready", workflow_phase="ready"),
    "completed_skip": StageDef("completed_skip", "ready", workflow_phase="ready"),
}


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

# Canonical topology name → stage graph
_TOPOLOGIES: Mapping[str, Mapping[str, StageDef]] = {
    "two_tank_drip_substrate_trays": TWO_TANK,
    "two_tank": TWO_TANK,  # short alias used in legacy intents
}


class TopologyRegistry:
    """Lookup service for stage definitions within a topology."""

    def __init__(
        self,
        topologies: Mapping[str, Mapping[str, StageDef]] | None = None,
    ) -> None:
        self._topologies = dict(topologies or _TOPOLOGIES)

    def get(self, topology: str, stage: str) -> StageDef:
        """Return the :class:`StageDef` for *topology* / *stage*.

        Raises :class:`KeyError` if the topology or stage is unknown.
        """
        topo = self._topologies.get(topology)
        if topo is None:
            raise KeyError(f"Unknown topology: {topology!r}")
        stage_def = topo.get(stage)
        if stage_def is None:
            raise KeyError(
                f"Unknown stage {stage!r} in topology {topology!r}"
            )
        return stage_def

    def stages(self, topology: str) -> Mapping[str, StageDef]:
        """Return the full stage graph for *topology*."""
        topo = self._topologies.get(topology)
        if topo is None:
            raise KeyError(f"Unknown topology: {topology!r}")
        return topo

    def has_topology(self, topology: str) -> bool:
        return topology in self._topologies

    def validate(self, topology: str) -> list[str]:
        """Return a list of validation errors (empty if graph is consistent)."""
        topo = self._topologies.get(topology)
        if topo is None:
            return [f"Unknown topology: {topology!r}"]
        errors: list[str] = []
        for name, sdef in topo.items():
            if sdef.name != name:
                errors.append(
                    f"Stage key {name!r} != StageDef.name {sdef.name!r}"
                )
            if sdef.next_stage and sdef.next_stage not in topo:
                errors.append(
                    f"Stage {name!r} references unknown next_stage "
                    f"{sdef.next_stage!r}"
                )
            if sdef.on_corr_success and sdef.on_corr_success not in topo:
                errors.append(
                    f"Stage {name!r} references unknown on_corr_success "
                    f"{sdef.on_corr_success!r}"
                )
            if sdef.on_corr_fail and sdef.on_corr_fail not in topo:
                errors.append(
                    f"Stage {name!r} references unknown on_corr_fail "
                    f"{sdef.on_corr_fail!r}"
                )
            if sdef.has_correction and not (
                sdef.on_corr_success and sdef.on_corr_fail
            ):
                errors.append(
                    f"Stage {name!r} has_correction=True but missing "
                    f"on_corr_success/on_corr_fail"
                )
            if sdef.terminal_error and sdef.next_stage:
                errors.append(
                    f"Stage {name!r} has both terminal_error and next_stage"
                )
        return errors
