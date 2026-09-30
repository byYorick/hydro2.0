"""Чтение плана зоны для AE4 без дефолтов AE3.

Источник — automation_effective_bundles активной посадки и фаза.
Нет ключа — ошибка конфигурации, не подстановка 900 или 100 л.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any, Mapping

from ae4.domain.dose_policy import ControllerDoseParams
from common.db import fetch


class ZonePlanConfigurationError(RuntimeError):
    """Обязательный ключ плана зоны отсутствует или пуст."""

    def __init__(self, *, reason_code: str, message: str) -> None:
        super().__init__(message)
        self.reason_code = reason_code


@dataclass(frozen=True)
class DoseActuatorRef:
    node_uid: str
    channel: str
    ml_per_sec: float | None = None


@dataclass(frozen=True)
class ZoneDosePlan:
    """Контроллеры и актуаторы импульса. Нет gain/max — импульса нет."""

    stale_ec_allows_shot: bool | None
    ec: ControllerDoseParams
    ph: ControllerDoseParams
    ph_up_gain: float | None
    ph_down_gain: float | None
    actuators: Mapping[str, DoseActuatorRef]


@dataclass(frozen=True)
class ZonePlan:
    zone_id: int
    grow_cycle_id: int
    greenhouse_id: int
    greenhouse_uid: str
    timezone: str
    control_mode: str
    telemetry_max_age_sec: int
    clean_fill_timeout_sec: int
    solution_topup_timeout_sec: int
    nutrient_solution_volume_l: float
    command_plans: Mapping[str, Any]
    dose: ZoneDosePlan | None = None
    stale_ec_allows_shot: bool | None = None
    ec_clean: float | None = None
    drain_tank_volume_l: float | None = None
    pump_main_ml_per_sec: float | None = None
    channel_node_uids: Mapping[str, str] | None = None


def _require_mapping(value: Any, *, path: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or not value:
        raise ZonePlanConfigurationError(
            reason_code="zone_plan_missing_key",
            message=f"Нет ключа плана зоны: {path}",
        )
    return value


def _require_int(value: Any, *, path: str) -> int:
    if value is None or isinstance(value, bool):
        raise ZonePlanConfigurationError(
            reason_code="zone_plan_missing_key",
            message=f"Нет ключа плана зоны: {path}",
        )
    try:
        number = int(value)
    except (TypeError, ValueError) as exc:
        raise ZonePlanConfigurationError(
            reason_code="zone_plan_invalid_value",
            message=f"Неверное значение плана зоны: {path}",
        ) from exc
    if number <= 0:
        raise ZonePlanConfigurationError(
            reason_code="zone_plan_invalid_value",
            message=f"Неверное значение плана зоны: {path}",
        )
    return number


def _require_float(value: Any, *, path: str) -> float:
    if value is None or isinstance(value, bool):
        raise ZonePlanConfigurationError(
            reason_code="zone_plan_missing_key",
            message=f"Нет ключа плана зоны: {path}",
        )
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ZonePlanConfigurationError(
            reason_code="zone_plan_invalid_value",
            message=f"Неверное значение плана зоны: {path}",
        ) from exc
    if number <= 0:
        raise ZonePlanConfigurationError(
            reason_code="zone_plan_invalid_value",
            message=f"Неверное значение плана зоны: {path}",
        )
    return number


def _dig(root: Mapping[str, Any], *keys: str) -> Any:
    current: Any = root
    for key in keys:
        if not isinstance(current, Mapping):
            return None
        current = current.get(key)
    return current


async def load_zone_plan(*, zone_id: int) -> ZonePlan:
    """Читает bundle посадки и фазу fail-closed, без дефолтов AE3."""
    rows = await fetch(
        """
        SELECT
            zones.id AS zone_id,
            zones.control_mode,
            zones.greenhouse_id AS greenhouse_id,
            greenhouses.uid AS greenhouse_uid,
            greenhouses.timezone AS timezone,
            gc.id AS grow_cycle_id,
            gcp.nutrient_solution_volume_l AS nutrient_solution_volume_l,
            bundles.config AS bundle_config
        FROM zones
        JOIN greenhouses ON greenhouses.id = zones.greenhouse_id
        LEFT JOIN grow_cycles AS gc
            ON gc.zone_id = zones.id
           AND gc.status IN ('PLANNED', 'RUNNING', 'PAUSED')
        LEFT JOIN grow_cycle_phases AS gcp
            ON gcp.id = gc.current_phase_id
        LEFT JOIN automation_effective_bundles AS bundles
            ON bundles.scope_type = 'grow_cycle'
           AND bundles.scope_id = gc.id
        WHERE zones.id = $1
        ORDER BY
            CASE gc.status
                WHEN 'RUNNING' THEN 1
                WHEN 'PAUSED' THEN 2
                WHEN 'PLANNED' THEN 3
                ELSE 4
            END,
            gc.id DESC
        LIMIT 1
        """,
        zone_id,
    )
    if not rows:
        raise ZonePlanConfigurationError(
            reason_code="zone_not_found",
            message=f"Зона {zone_id} не найдена",
        )
    row = rows[0]
    timezone = str(row.get("timezone") or "").strip()
    if not timezone:
        raise ZonePlanConfigurationError(
            reason_code="zone_plan_missing_timezone",
            message="Пустой timezone теплицы — ошибка конфигурации",
        )
    greenhouse_uid = str(row.get("greenhouse_uid") or "").strip()
    if not greenhouse_uid:
        raise ZonePlanConfigurationError(
            reason_code="zone_plan_missing_greenhouse",
            message="Нет greenhouse_uid у зоны",
        )
    grow_cycle_id = row.get("grow_cycle_id")
    if grow_cycle_id is None:
        raise ZonePlanConfigurationError(
            reason_code="zone_plan_missing_grow_cycle",
            message="Нет активной посадки у зоны",
        )
    bundle_config = row.get("bundle_config")
    if not isinstance(bundle_config, Mapping):
        raise ZonePlanConfigurationError(
            reason_code="zone_plan_missing_bundle",
            message="Нет automation_effective_bundle у посадки",
        )

    zone_bundle = _require_mapping(
        bundle_config.get("zone"),
        path="bundle.zone",
    )
    logic_profile = _require_mapping(
        zone_bundle.get("logic_profile"),
        path="bundle.zone.logic_profile",
    )
    active_profile = logic_profile.get("active_profile")
    if not isinstance(active_profile, Mapping):
        active_profile = logic_profile
    command_plans = active_profile.get("command_plans")
    if not isinstance(command_plans, Mapping) or not command_plans:
        raise ZonePlanConfigurationError(
            reason_code="zone_plan_missing_command_plans",
            message="Нет command_plans у зоны",
        )

    correction_root: Mapping[str, Any] = {}
    correction_bundle = zone_bundle.get("correction")
    if isinstance(correction_bundle, Mapping):
        resolved = correction_bundle.get("resolved_config")
        if isinstance(resolved, Mapping):
            correction_root = resolved

    telemetry_max_age_sec = _require_int(
        _dig(correction_root, "timing", "telemetry_max_age_sec")
        or _dig(correction_root, "base", "timing", "telemetry_max_age_sec")
        or _dig(
            correction_root,
            "phases",
            "solution_fill",
            "timing",
            "telemetry_max_age_sec",
        ),
        path="correction_config.timing.telemetry_max_age_sec",
    )
    clean_fill_timeout_sec = _require_int(
        _dig(correction_root, "runtime", "clean_fill_timeout_sec")
        or _dig(correction_root, "base", "runtime", "clean_fill_timeout_sec")
        or _dig(
            correction_root,
            "phases",
            "solution_fill",
            "runtime",
            "clean_fill_timeout_sec",
        ),
        path="runtime.clean_fill_timeout_sec",
    )
    # Каталог Laravel пишет solution_fill_timeout_sec. AE держит то же окно как topup.
    solution_topup_timeout_sec = _require_int(
        _dig(correction_root, "runtime", "solution_topup_timeout_sec")
        or _dig(correction_root, "runtime", "solution_fill_timeout_sec")
        or _dig(correction_root, "base", "runtime", "solution_topup_timeout_sec")
        or _dig(correction_root, "base", "runtime", "solution_fill_timeout_sec")
        or _dig(
            correction_root,
            "phases",
            "solution_fill",
            "runtime",
            "solution_topup_timeout_sec",
        )
        or _dig(
            correction_root,
            "phases",
            "solution_fill",
            "runtime",
            "solution_fill_timeout_sec",
        ),
        path="runtime.solution_topup_timeout_sec",
    )

    nutrient_solution_volume_l = _require_float(
        row.get("nutrient_solution_volume_l"),
        path="grow_cycle_phases.nutrient_solution_volume_l",
    )

    stale_ec_allows_shot = _parse_stale_ec_allows_shot(correction_root)
    ec_clean = _parse_ec_clean(correction_root)
    dose = _build_dose_plan(
        correction_root=correction_root,
        zone_bundle=zone_bundle,
        stale_ec_allows_shot=stale_ec_allows_shot,
    )
    dose = await _attach_channel_dose_rates(zone_id=int(row["zone_id"]), dose=dose)
    pump_main_ml_per_sec = None
    if dose is not None:
        nutrition = dose.actuators.get("nutrition")
        if nutrition is not None and nutrition.ml_per_sec:
            pump_main_ml_per_sec = float(nutrition.ml_per_sec)
    if pump_main_ml_per_sec is None:
        pump = correction_root.get("pump_calibration")
        if isinstance(pump, Mapping):
            pump_main_ml_per_sec = _optional_float(pump.get("ml_per_sec"))

    return ZonePlan(
        zone_id=int(row["zone_id"]),
        grow_cycle_id=int(grow_cycle_id),
        greenhouse_id=int(row["greenhouse_id"]),
        greenhouse_uid=greenhouse_uid,
        timezone=timezone,
        control_mode=str(row.get("control_mode") or "auto").strip().lower() or "auto",
        telemetry_max_age_sec=telemetry_max_age_sec,
        clean_fill_timeout_sec=clean_fill_timeout_sec,
        solution_topup_timeout_sec=solution_topup_timeout_sec,
        nutrient_solution_volume_l=nutrient_solution_volume_l,
        command_plans=dict(command_plans),
        dose=dose,
        stale_ec_allows_shot=stale_ec_allows_shot,
        ec_clean=ec_clean,
        drain_tank_volume_l=None,
        pump_main_ml_per_sec=pump_main_ml_per_sec,
        channel_node_uids=await _channel_node_uids(zone_id=int(row["zone_id"])),
    )


_REAGENT_CHANNELS = {
    "nutrition": "pump_a",
    "ph_up": "pump_base",
    "ph_down": "pump_acid",
}


async def _attach_channel_dose_rates(*, zone_id: int, dose: ZoneDosePlan) -> ZoneDosePlan:
    """ml/сек активной калибровки канала, если в bundle его нет."""
    rows = await fetch(
        """
        SELECT LOWER(nc.channel) AS channel, pc.ml_per_sec
        FROM pump_calibrations AS pc
        JOIN node_channels AS nc ON nc.id = pc.node_channel_id
        JOIN nodes AS n ON n.id = nc.node_id
        WHERE (n.zone_id = $1 OR n.pending_zone_id = $1)
          AND pc.is_active = true
          AND pc.ml_per_sec > 0
          AND (pc.valid_to IS NULL OR pc.valid_to > NOW())
        """,
        zone_id,
    )
    rates: dict[str, float] = {}
    for row in rows:
        channel = str(row.get("channel") or "").strip()
        ml = _optional_float(row.get("ml_per_sec"))
        if channel and ml and ml > 0:
            rates[channel] = ml
    if not rates:
        return dose
    nutrition_ml = dose.ec.ml_per_sec or rates.get("pump_a")
    ph_ml = dose.ph.ml_per_sec or rates.get("pump_acid") or rates.get("pump_base")
    actuators = dict(dose.actuators)
    for reagent, channel in _REAGENT_CHANNELS.items():
        current = actuators.get(reagent)
        ml = None
        if current is not None and current.ml_per_sec:
            ml = current.ml_per_sec
        else:
            ml = rates.get(channel)
        if current is None and ml is None:
            continue
        actuators[reagent] = DoseActuatorRef(
            node_uid=current.node_uid if current is not None else "",
            channel=current.channel if current is not None and current.channel else channel,
            ml_per_sec=ml,
        )
    return replace(
        dose,
        ec=replace(dose.ec, ml_per_sec=nutrition_ml),
        ph=replace(dose.ph, ml_per_sec=ph_ml),
        actuators=actuators,
    )


async def _channel_node_uids(*, zone_id: int) -> dict[str, str]:
    """Канал → uid узла из привязок зоны. Шаги плана часто без node_uid."""
    rows = await fetch(
        """
        SELECT nc.channel AS channel, n.uid AS node_uid
        FROM nodes AS n
        JOIN node_channels AS nc ON nc.node_id = n.id
        WHERE n.zone_id = $1
           OR n.id IN (
                SELECT nc2.node_id
                FROM channel_bindings AS cb
                JOIN node_channels AS nc2 ON nc2.id = cb.node_channel_id
                JOIN infrastructure_instances AS ii
                  ON ii.id = cb.infrastructure_instance_id
                WHERE ii.owner_type = 'zone' AND ii.owner_id = $1
           )
        """,
        zone_id,
    )
    mapped: dict[str, str] = {}
    for row in rows:
        channel = str(row.get("channel") or "").strip()
        node_uid = str(row.get("node_uid") or "").strip()
        if channel and node_uid:
            mapped[channel] = node_uid
    return mapped


def _parse_stale_ec_allows_shot(correction_root: Mapping[str, Any]) -> bool | None:
    """Пусто = deny. Явные allow/deny. Дефолт AE3 не подставляется."""
    raw = _dig(correction_root, "timing", "stale_ec_allows_shot")
    if raw is None:
        raw = _dig(correction_root, "base", "timing", "stale_ec_allows_shot")
    if raw is None:
        return None
    if isinstance(raw, bool):
        return raw
    text = str(raw).strip().lower()
    if text == "":
        return None
    if text in {"allow", "true", "1", "yes"}:
        return True
    if text in {"deny", "false", "0", "no"}:
        return False
    return None


def _parse_ec_clean(correction_root: Mapping[str, Any]) -> float | None:
    """Пустое поле долю слива не считает. Каталожное число не подставляется."""
    raw = _dig(correction_root, "timing", "ec_clean")
    if raw is None:
        raw = _dig(correction_root, "base", "timing", "ec_clean")
    number = _optional_float(raw)
    if number is None:
        return None
    if number < 0:
        return None
    return number


def _optional_float(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number


def _optional_int(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    return number


def _controller_mapping(correction_root: Mapping[str, Any], kind: str) -> Mapping[str, Any]:
    """Контроллер лежит в `controllers` или, в compiled bundle, в `base.controllers`."""
    direct = _dig(correction_root, "controllers", kind)
    if isinstance(direct, Mapping) and direct:
        return direct
    nested = _dig(correction_root, "base", "controllers", kind)
    if isinstance(nested, Mapping):
        return nested
    return {}


def _controller_params(
    *,
    correction_root: Mapping[str, Any],
    kind: str,
    gain: float | None,
    min_dose_ms: int | None,
    ml_per_sec: float | None,
) -> ControllerDoseParams:
    ctrl = _controller_mapping(correction_root, kind)
    observe = ctrl.get("observe") if isinstance(ctrl.get("observe"), Mapping) else {}
    return ControllerDoseParams(
        gain=gain,
        max_dose_ml=_optional_float(ctrl.get("max_dose_ml")),
        min_interval_sec=_optional_int(ctrl.get("min_interval_sec")),
        decision_window_sec=_optional_int(observe.get("decision_window_sec")),
        min_effect_fraction=_optional_float(observe.get("min_effect_fraction")),
        no_effect_limit=_optional_int(observe.get("no_effect_consecutive_limit")),
        min_dose_ms=min_dose_ms,
        ml_per_sec=ml_per_sec,
    )


def _process_gains(zone_bundle: Mapping[str, Any]) -> dict[str, float | None]:
    """Gain из process_calibration зоны. Пусто — не подставляем."""
    calibrations = zone_bundle.get("process_calibration")
    phase_cfg: Mapping[str, Any] = {}
    if isinstance(calibrations, Mapping):
        for key in ("irrigation", "tank_recirc", "solution_fill", "generic"):
            entry = calibrations.get(key)
            if isinstance(entry, Mapping) and entry:
                phase_cfg = entry
                break
    return {
        "ec": _optional_float(phase_cfg.get("ec_gain_per_ml")),
        "ph_up": _optional_float(phase_cfg.get("ph_up_gain_per_ml")),
        "ph_down": _optional_float(phase_cfg.get("ph_down_gain_per_ml")),
    }


def _actuator_from_mapping(raw: Any) -> DoseActuatorRef | None:
    if not isinstance(raw, Mapping):
        return None
    node_uid = str(raw.get("node_uid") or "").strip()
    channel = str(raw.get("channel") or "").strip()
    if not node_uid or not channel:
        return None
    calibration = raw.get("calibration") if isinstance(raw.get("calibration"), Mapping) else {}
    ml = _optional_float(calibration.get("ml_per_sec") or raw.get("ml_per_sec"))
    return DoseActuatorRef(node_uid=node_uid, channel=channel, ml_per_sec=ml)


def _build_dose_plan(
    *,
    correction_root: Mapping[str, Any],
    zone_bundle: Mapping[str, Any],
    stale_ec_allows_shot: bool | None,
) -> ZoneDosePlan:
    gains = _process_gains(zone_bundle)
    pump = correction_root.get("pump_calibration")
    if not isinstance(pump, Mapping):
        pump = {}
    min_dose_ms = _optional_int(pump.get("min_dose_ms"))
    ml_per_sec = _optional_float(pump.get("ml_per_sec"))

    actuators_raw = correction_root.get("actuators")
    actuators: dict[str, DoseActuatorRef] = {}
    if isinstance(actuators_raw, Mapping):
        for key, reagent in (
            ("ec", "nutrition"),
            ("ph_up", "ph_up"),
            ("ph_down", "ph_down"),
        ):
            ref = _actuator_from_mapping(actuators_raw.get(key))
            if ref is not None:
                actuators[reagent] = ref

    dosing = correction_root.get("dosing")
    if isinstance(dosing, Mapping):
        channel_map = {
            "nutrition": str(dosing.get("dose_ec_channel") or "").strip(),
            "ph_up": str(dosing.get("dose_ph_up_channel") or "").strip(),
            "ph_down": str(dosing.get("dose_ph_down_channel") or "").strip(),
        }
        for reagent, channel in channel_map.items():
            if reagent in actuators or not channel:
                continue
            # Канал известен, node_uid подставит execute по узлам зоны.
            actuators[reagent] = DoseActuatorRef(
                node_uid="",
                channel=channel,
                ml_per_sec=ml_per_sec,
            )

    nutrition_ml = actuators.get("nutrition").ml_per_sec if "nutrition" in actuators else ml_per_sec
    ph_ml = None
    for key in ("ph_up", "ph_down"):
        if key in actuators and actuators[key].ml_per_sec:
            ph_ml = actuators[key].ml_per_sec
            break
    if ph_ml is None:
        ph_ml = ml_per_sec

    return ZoneDosePlan(
        stale_ec_allows_shot=stale_ec_allows_shot,
        ec=_controller_params(
            correction_root=correction_root,
            kind="ec",
            gain=gains["ec"],
            min_dose_ms=min_dose_ms,
            ml_per_sec=nutrition_ml,
        ),
        ph=_controller_params(
            correction_root=correction_root,
            kind="ph",
            gain=gains["ph_up"],  # для оценки; pH-down gain отдельно в ZoneDosePlan
            min_dose_ms=min_dose_ms,
            ml_per_sec=ph_ml,
        ),
        ph_up_gain=gains["ph_up"],
        ph_down_gain=gains["ph_down"],
        actuators=actuators,
    )


def require_plan_steps(
    plan: ZonePlan,
    *,
    plan_key: str,
) -> list[Mapping[str, Any]]:
    """Возвращает список шагов command plan; имени ключа в gateway нет."""
    plans_root = plan.command_plans.get("plans")
    if not isinstance(plans_root, Mapping):
        plans_root = plan.command_plans
    steps = plans_root.get(plan_key) if isinstance(plans_root, Mapping) else None
    if not isinstance(steps, list) or not steps:
        diagnostics = plans_root.get("diagnostics") if isinstance(plans_root, Mapping) else None
        two_tank = diagnostics.get("two_tank_commands") if isinstance(diagnostics, Mapping) else None
        if isinstance(two_tank, Mapping):
            steps = two_tank.get(plan_key)
    if not isinstance(steps, list) or not steps:
        raise ZonePlanConfigurationError(
            reason_code="zone_plan_missing_steps",
            message=f"Нет шагов плана зоны: {plan_key}",
        )
    normalized: list[Mapping[str, Any]] = []
    for index, step in enumerate(steps):
        if not isinstance(step, Mapping):
            raise ZonePlanConfigurationError(
                reason_code="zone_plan_invalid_step",
                message=f"Шаг {plan_key}[{index}] не объект",
            )
        channel = str(step.get("channel") or "").strip()
        cmd = str(step.get("cmd") or "").strip()
        if not channel or not cmd:
            raise ZonePlanConfigurationError(
                reason_code="zone_plan_invalid_step",
                message=f"Шаг {plan_key}[{index}] без channel/cmd",
            )
        params = step.get("params")
        if params is None:
            params = {}
        if not isinstance(params, Mapping):
            raise ZonePlanConfigurationError(
                reason_code="zone_plan_invalid_step",
                message=f"Шаг {plan_key}[{index}] params не объект",
            )
        node_uid = str(step.get("node_uid") or "").strip()
        if not node_uid and plan.channel_node_uids:
            node_uid = str(plan.channel_node_uids.get(channel) or "").strip()
        normalized.append(
            {
                "node_uid": node_uid,
                "channel": channel,
                "cmd": cmd,
                "params": dict(params),
            }
        )
    return normalized


__all__ = [
    "DoseActuatorRef",
    "ZoneDosePlan",
    "ZonePlan",
    "ZonePlanConfigurationError",
    "load_zone_plan",
    "require_plan_steps",
]
