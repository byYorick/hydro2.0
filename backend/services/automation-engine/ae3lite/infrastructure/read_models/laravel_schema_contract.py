"""AE3 read-model contract: таблицы и колонки PostgreSQL, от которых зависит automation-engine.

Инварианты, которые обязан удерживать Laravel (владелец миграций):

* Каждая перечисленная таблица существует.
* Каждая required-колонка существует и имеет совместимый тип (см. ``TYPE_FAMILIES``).
* Для required-enum/literal значения (``enum_values``) хотя бы одна строка либо
  допустимость этого значения в CHECK-constraint должна присутствовать.
  Проверку чаще всего делает ``test_read_model_contract.py`` по committed snapshot.

Когда AE3 начинает читать новую колонку / новое enum-значение — ОБЯЗАНО появиться и здесь.
Валидатор падает, если миграция Laravel уронила required-колонку или переименовала её.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import FrozenSet, Mapping


TYPE_FAMILIES: Mapping[str, FrozenSet[str]] = {
    "integer": frozenset({"integer", "int4", "int", "smallint", "int2"}),
    "bigint": frozenset({"bigint", "int8"}),
    "text": frozenset({"text", "character varying", "varchar", "character", "char", "citext"}),
    "timestamp": frozenset({"timestamp without time zone", "timestamp with time zone", "timestamp", "timestamptz"}),
    "jsonb": frozenset({"jsonb", "json"}),
    "boolean": frozenset({"boolean", "bool"}),
    "numeric": frozenset({"numeric", "decimal", "double precision", "real", "float8", "float4"}),
    "uuid": frozenset({"uuid"}),
    "bytea": frozenset({"bytea"}),
    "interval": frozenset({"interval"}),
    "inet": frozenset({"inet"}),
    "array": frozenset({"ARRAY"}),
    "time": frozenset({"time without time zone", "time with time zone", "time", "timetz"}),
}


@dataclass(frozen=True)
class Column:
    name: str
    type_family: str
    nullable: bool = True

    def __post_init__(self) -> None:
        if self.type_family not in TYPE_FAMILIES:
            raise ValueError(f"Unknown type_family={self.type_family!r} for column {self.name!r}")


@dataclass(frozen=True)
class Table:
    name: str
    columns: tuple[Column, ...]
    # column_name -> литералы, которые AE3 ждёт встретить (IN / =).
    enum_values: Mapping[str, frozenset[str]] = field(default_factory=dict)


def _col(name: str, fam: str, nullable: bool = True) -> Column:
    return Column(name=name, type_family=fam, nullable=nullable)


# ----------------------------------------------------------------------------
# AE3-owned tables (AE3 is primary writer + reader)
# ----------------------------------------------------------------------------

AE_TASKS = Table(
    name="ae_tasks",
    columns=(
        _col("id", "bigint", nullable=False),
        _col("zone_id", "bigint", nullable=False),
        _col("status", "text", nullable=False),
        _col("idempotency_key", "text"),
        _col("claimed_by", "text"),
        _col("claimed_at", "timestamp"),
        _col("due_at", "timestamp"),
        _col("created_at", "timestamp", nullable=False),
        _col("updated_at", "timestamp", nullable=False),
        _col("intent_source", "text"),
        _col("intent_trigger", "text"),
        _col("intent_id", "bigint"),
        _col("intent_meta", "jsonb"),
        _col("task_type", "text"),
        _col("topology", "text"),
        _col("current_stage", "text"),
        _col("workflow_phase", "text"),
        _col("error_code", "text"),
        _col("error_message", "text"),
        _col("completed_at", "timestamp"),
        _col("stage_deadline_at", "timestamp"),
        _col("stage_retry_count", "integer"),
        _col("stage_entered_at", "timestamp"),
        _col("clean_fill_cycle", "integer"),
        _col("control_mode_snapshot", "text"),
        _col("pending_manual_step", "text"),
        _col("start_event_emitted", "boolean"),
        _col("irr_probe_failure_streak", "integer"),
        _col("irrigation_mode", "text"),
        _col("irrigation_requested_duration_sec", "integer"),
        _col("irrigation_replay_count", "integer"),
        _col("irrigation_wait_ready_deadline_at", "timestamp"),
        _col("irrigation_setup_deadline_at", "timestamp"),
    ),
    enum_values={
        "status": frozenset({"pending", "claimed", "running", "waiting_command", "completed", "failed"}),
        "task_type": frozenset({"cycle_start", "irrigation_start", "lighting_tick"}),
    },
)

AE_COMMANDS = Table(
    name="ae_commands",
    columns=(
        _col("id", "bigint", nullable=False),
        _col("task_id", "bigint", nullable=False),
        _col("step_no", "integer", nullable=False),
        _col("node_uid", "text", nullable=False),
        _col("channel", "text", nullable=False),
        _col("payload", "jsonb", nullable=False),
        _col("stage_name", "text"),
        _col("publish_status", "text", nullable=False),
        _col("external_id", "text"),
        _col("ack_received_at", "timestamp"),
        _col("terminal_status", "text"),
        _col("terminal_at", "timestamp"),
        _col("last_error", "text"),
        _col("created_at", "timestamp", nullable=False),
        _col("updated_at", "timestamp", nullable=False),
    ),
    enum_values={
        "publish_status": frozenset({"pending", "accepted", "failed"}),
    },
)

AE_STAGE_TRANSITIONS = Table(
    name="ae_stage_transitions",
    columns=(
        _col("task_id", "bigint", nullable=False),
        _col("from_stage", "text"),
        _col("to_stage", "text", nullable=False),
        _col("workflow_phase", "text"),
        _col("triggered_at", "timestamp", nullable=False),
        _col("metadata", "jsonb"),
    ),
)

AE_ZONE_LEASES = Table(
    name="ae_zone_leases",
    columns=(
        _col("zone_id", "bigint", nullable=False),
        _col("owner", "text", nullable=False),
        _col("leased_until", "timestamp", nullable=False),
        _col("updated_at", "timestamp", nullable=False),
    ),
)

PID_STATE = Table(
    name="pid_state",
    columns=(
        _col("zone_id", "bigint", nullable=False),
        _col("pid_type", "text", nullable=False),
        _col("integral", "numeric"),
        _col("prev_error", "numeric"),
        _col("prev_derivative", "numeric"),
        _col("last_output_ms", "bigint"),
        _col("last_dose_at", "timestamp"),
        _col("hold_until", "timestamp"),
        _col("last_measurement_at", "timestamp"),
        _col("last_measured_value", "numeric"),
        _col("feedforward_bias", "numeric"),
        _col("no_effect_count", "integer"),
        _col("last_correction_kind", "text"),
        _col("stats", "jsonb"),
        _col("created_at", "timestamp", nullable=False),
        _col("updated_at", "timestamp", nullable=False),
    ),
    enum_values={
        "pid_type": frozenset({"ec", "ph"}),
    },
)

ZONE_WORKFLOW_STATE = Table(
    name="zone_workflow_state",
    columns=(
        _col("zone_id", "bigint", nullable=False),
        _col("workflow_phase", "text", nullable=False),
        _col("version", "bigint", nullable=False),
        _col("started_at", "timestamp"),
        _col("updated_at", "timestamp", nullable=False),
        _col("payload", "jsonb"),
        _col("scheduler_task_id", "text"),
    ),
)


# ----------------------------------------------------------------------------
# Laravel-owned (AE3 reads write-through from Laravel)
# ----------------------------------------------------------------------------

ZONE_AUTOMATION_INTENTS = Table(
    name="zone_automation_intents",
    columns=(
        _col("id", "bigint", nullable=False),
        _col("zone_id", "bigint", nullable=False),
        _col("status", "text", nullable=False),
        _col("idempotency_key", "text"),
        _col("claimed_at", "timestamp"),
        _col("updated_at", "timestamp", nullable=False),
        _col("retry_count", "integer"),
        _col("max_retries", "integer"),
        _col("not_before", "timestamp"),
        _col("topology", "text"),
        _col("task_type", "text"),
        _col("intent_type", "text"),
        _col("intent_source", "text"),
        _col("irrigation_mode", "text"),
        _col("irrigation_requested_duration_sec", "integer"),
        _col("completed_at", "timestamp"),
        _col("error_code", "text"),
        _col("error_message", "text"),
    ),
    enum_values={
        "status": frozenset({"pending", "claimed", "running", "failed", "completed", "cancelled"}),
        "task_type": frozenset({"cycle_start", "irrigation_start", "lighting_tick"}),
    },
)

ZONES = Table(
    name="zones",
    columns=(
        _col("id", "bigint", nullable=False),
        _col("greenhouse_id", "bigint"),
        _col("control_mode", "text"),
        _col("settings", "jsonb"),
        _col("updated_at", "timestamp"),
    ),
    enum_values={
        "control_mode": frozenset({"auto", "manual", "semi"}),
    },
)

GREENHOUSES = Table(
    name="greenhouses",
    columns=(
        _col("id", "bigint", nullable=False),
        _col("uid", "text"),
        _col("timezone", "text"),
    ),
)

GROW_CYCLES = Table(
    name="grow_cycles",
    columns=(
        _col("id", "bigint", nullable=False),
        _col("zone_id", "bigint", nullable=False),
        _col("current_phase_id", "bigint"),
        _col("status", "text", nullable=False),
        _col("settings", "jsonb"),
    ),
    enum_values={
        "status": frozenset({"PLANNED", "RUNNING", "PAUSED"}),
    },
)

GROW_CYCLE_PHASES = Table(
    name="grow_cycle_phases",
    columns=(
        _col("id", "bigint", nullable=False),
        _col("name", "text"),
        _col("ph_target", "numeric"),
        _col("ph_min", "numeric"),
        _col("ph_max", "numeric"),
        _col("ec_target", "numeric"),
        _col("ec_min", "numeric"),
        _col("ec_max", "numeric"),
        _col("irrigation_mode", "text"),
        _col("irrigation_system_type", "text"),
        _col("substrate_type", "text"),
        _col("day_night_enabled", "boolean"),
        _col("irrigation_interval_sec", "integer"),
        _col("irrigation_duration_sec", "integer"),
        _col("lighting_photoperiod_hours", "integer"),
        _col("lighting_start_time", "time"),
        _col("temp_air_target", "numeric"),
        _col("humidity_target", "numeric"),
        _col("co2_target", "integer"),
        _col("mist_interval_sec", "integer"),
        _col("mist_duration_sec", "integer"),
        _col("mist_mode", "text"),
        _col("extensions", "jsonb"),
    ),
)

AUTOMATION_EFFECTIVE_BUNDLES = Table(
    name="automation_effective_bundles",
    columns=(
        _col("scope_type", "text", nullable=False),
        _col("scope_id", "bigint", nullable=False),
        _col("bundle_revision", "text"),
        _col("config", "jsonb", nullable=False),
    ),
    enum_values={
        "scope_type": frozenset({"zone", "grow_cycle"}),
    },
)

AUTOMATION_CONFIG_DOCUMENTS = Table(
    name="automation_config_documents",
    columns=(
        _col("namespace", "text", nullable=False),
        _col("scope_type", "text", nullable=False),
        _col("scope_id", "bigint", nullable=False),
        _col("payload", "jsonb", nullable=False),
    ),
    enum_values={
        "namespace": frozenset({"zone.correction"}),
        "scope_type": frozenset({"zone", "grow_cycle"}),
    },
)

SENSORS = Table(
    name="sensors",
    columns=(
        _col("id", "bigint", nullable=False),
        _col("label", "text"),
        _col("zone_id", "bigint"),
        _col("is_active", "boolean", nullable=False),
        _col("type", "text", nullable=False),
    ),
    enum_values={
        "type": frozenset({"WATER_LEVEL", "WATER_LEVEL_SWITCH"}),
    },
)

TELEMETRY_LAST = Table(
    name="telemetry_last",
    columns=(
        _col("sensor_id", "bigint", nullable=False),
        _col("last_value", "numeric"),
        _col("last_ts", "timestamp"),
        _col("last_quality", "text"),
        _col("updated_at", "timestamp"),
    ),
)

TELEMETRY_SAMPLES = Table(
    name="telemetry_samples",
    columns=(
        _col("id", "bigint"),
        _col("sensor_id", "bigint", nullable=False),
        _col("ts", "timestamp", nullable=False),
        _col("value", "numeric"),
    ),
)

ZONE_EVENTS = Table(
    name="zone_events",
    columns=(
        _col("id", "bigint"),
        _col("zone_id", "bigint", nullable=False),
        _col("type", "text", nullable=False),
        _col("payload_json", "jsonb"),
        _col("created_at", "timestamp", nullable=False),
    ),
    enum_values={
        # AE3 производит INSERT с этими type'ами и читает их из LATERAL history.
        "type": frozenset({
            "LEVEL_SWITCH_CHANGED",
            "IRR_STATE_SNAPSHOT",
            "AE_TASK_STARTED",
            "IRRIGATION_DECISION_SNAPSHOT_LOCKED",
        }),
    },
)

NODES = Table(
    name="nodes",
    columns=(
        _col("id", "bigint", nullable=False),
        _col("uid", "text", nullable=False),
        _col("type", "text"),
        _col("status", "text"),
        _col("zone_id", "bigint"),
        _col("last_seen_at", "timestamp"),
        _col("last_heartbeat_at", "timestamp"),
    ),
)

NODE_CHANNELS = Table(
    name="node_channels",
    columns=(
        _col("id", "bigint", nullable=False),
        _col("node_id", "bigint", nullable=False),
        _col("channel", "text", nullable=False),
        _col("type", "text", nullable=False),
        _col("config", "jsonb"),
        _col("is_active", "boolean"),
    ),
    enum_values={
        "type": frozenset({"ACTUATOR", "SERVICE"}),
    },
)

CHANNEL_BINDINGS = Table(
    name="channel_bindings",
    columns=(
        _col("node_channel_id", "bigint", nullable=False),
        _col("role", "text", nullable=False),
    ),
)

PUMP_CALIBRATIONS = Table(
    name="pump_calibrations",
    columns=(
        _col("node_channel_id", "bigint", nullable=False),
        _col("ml_per_sec", "numeric"),
        _col("k_ms_per_ml_l", "numeric"),
        _col("component", "text"),
        _col("source", "text"),
        _col("quality_score", "numeric"),
        _col("sample_count", "integer"),
        _col("valid_from", "timestamp"),
        _col("valid_to", "timestamp"),
        _col("is_active", "boolean"),
    ),
)

ALERTS = Table(
    name="alerts",
    columns=(
        _col("id", "bigint", nullable=False),
        _col("zone_id", "bigint"),
        _col("code", "text", nullable=False),
        _col("status", "text", nullable=False),
        _col("severity", "text"),
    ),
    enum_values={
        "status": frozenset({"ACTIVE"}),
        "severity": frozenset({"CRITICAL", "ERROR", "WARNING"}),
    },
)

COMMANDS = Table(
    name="commands",
    columns=(
        _col("id", "bigint", nullable=False),
        _col("zone_id", "bigint"),
        _col("node_id", "bigint"),
        _col("channel", "text"),
        _col("cmd", "text"),
        _col("params", "jsonb"),
        _col("source", "text"),
        _col("cycle_id", "bigint"),
        _col("cmd_id", "text"),
        _col("status", "text"),
        _col("ack_at", "timestamp"),
        _col("sent_at", "timestamp"),
        _col("failed_at", "timestamp"),
        _col("updated_at", "timestamp"),
        _col("created_at", "timestamp"),
        _col("error_message", "text"),
    ),
)

UNASSIGNED_NODE_ERRORS = Table(
    name="unassigned_node_errors",
    columns=(
        _col("hardware_id", "text", nullable=False),
        _col("error_message", "text"),
        _col("error_code", "text"),
        _col("severity", "text"),
        _col("topic", "text"),
        _col("last_payload", "jsonb"),
        _col("count", "integer"),
        _col("first_seen_at", "timestamp"),
        _col("last_seen_at", "timestamp"),
        _col("updated_at", "timestamp"),
    ),
)


ALL_TABLES: tuple[Table, ...] = (
    AE_TASKS,
    AE_COMMANDS,
    AE_STAGE_TRANSITIONS,
    AE_ZONE_LEASES,
    PID_STATE,
    ZONE_WORKFLOW_STATE,
    ZONE_AUTOMATION_INTENTS,
    ZONES,
    GREENHOUSES,
    GROW_CYCLES,
    GROW_CYCLE_PHASES,
    AUTOMATION_EFFECTIVE_BUNDLES,
    AUTOMATION_CONFIG_DOCUMENTS,
    SENSORS,
    TELEMETRY_LAST,
    TELEMETRY_SAMPLES,
    ZONE_EVENTS,
    NODES,
    NODE_CHANNELS,
    CHANNEL_BINDINGS,
    PUMP_CALIBRATIONS,
    ALERTS,
    COMMANDS,
    UNASSIGNED_NODE_ERRORS,
)

# LISTEN-каналы, которые AE3 подписывается на получение (NOTIFY шлёт Laravel/trigger).
NOTIFY_CHANNELS: frozenset[str] = frozenset({
    "scheduler_intent_terminal",
    "ae_zone_event",
})


def get_table(name: str) -> Table:
    for tbl in ALL_TABLES:
        if tbl.name == name:
            return tbl
    raise KeyError(name)
