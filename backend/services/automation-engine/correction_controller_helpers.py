"""Helper methods extracted from CorrectionController."""

import logging
import time
from typing import Any, Dict, List, Optional

from common.db import fetch
from config.settings import get_settings
from correction_ec_batch import (
    build_actuator_identity,
    build_ec_component_batch,
    extract_nutrition_control,
    get_latest_ec_value,
    resolve_batch_dose_control,
    resolve_ec_component_ratios,
    resolve_nutrition_mode,
    resolve_solution_volume_l,
)
from services.pid_config_service import get_config
from utils.adaptive_pid import AdaptivePid, AdaptivePidConfig, PidZone, PidZoneCoeffs

logger = logging.getLogger(__name__)


async def get_pid_for_zone(controller: Any, zone_id: int, setpoint: float) -> AdaptivePid:
    """Получить/инициализировать PID для зоны с восстановлением состояния."""
    pid = controller._pid_by_zone.get(zone_id)

    if pid is None:
        pid_config = await get_config(zone_id, controller.correction_type.value, setpoint)
        if pid_config is None:
            settings = get_settings()
            pid_config = controller._build_pid_config(settings, setpoint)
        pid = AdaptivePid(pid_config)

        await controller.pid_state_manager.restore_pid_state(
            zone_id,
            controller.correction_type.value,
            pid,
        )

        controller._pid_by_zone[zone_id] = pid
        controller._last_pid_tick[zone_id] = time.monotonic()
    else:
        pid.update_setpoint(setpoint)

    return pid


async def save_all_pid_states_for_controller(controller: Any) -> None:
    """Сохранить состояние всех PID контроллеров этого типа."""
    for zone_id, pid in controller._pid_by_zone.items():
        await controller.pid_state_manager.save_pid_state(
            zone_id,
            controller.correction_type.value,
            pid,
        )


def get_dt_seconds_for_zone(controller: Any, zone_id: int) -> float:
    """Рассчитать dt между вызовами PID для зоны с защитным clamping."""
    now = time.monotonic()
    last_tick = controller._last_pid_tick.get(zone_id)
    controller._last_pid_tick[zone_id] = now
    settings = get_settings()
    dt_min = max(0.0, float(getattr(settings, "PID_DT_MIN_SECONDS", 5.0)))
    dt_max = max(dt_min, float(getattr(settings, "PID_DT_MAX_SECONDS", 300.0)))

    if last_tick is None:
        default_dt = float(settings.MAIN_LOOP_SLEEP_SECONDS)
        return max(dt_min, min(default_dt, dt_max))

    raw_dt = now - last_tick
    clamped_dt = max(dt_min, min(raw_dt, dt_max))
    if raw_dt > dt_max:
        logger.warning(
            "PID dt clamped: raw_dt=%.1f sec > %.1fs (AE may have been paused), using %.1fs",
            raw_dt,
            dt_max,
            clamped_dt,
            extra={"zone_id": zone_id, "raw_dt_sec": round(raw_dt, 1)},
        )
    return clamped_dt


def build_pid_config_for_controller(controller: Any, settings: Any, setpoint: float) -> AdaptivePidConfig:
    """Сконфигурировать PID под тип коррекции."""
    is_ph = controller.correction_type.value == "ph"
    if is_ph:
        return AdaptivePidConfig(
            setpoint=setpoint,
            dead_zone=settings.PH_PID_DEAD_ZONE,
            close_zone=settings.PH_PID_CLOSE_ZONE,
            far_zone=settings.PH_PID_FAR_ZONE,
            zone_coeffs={
                PidZone.DEAD: PidZoneCoeffs(0.0, 0.0, 0.0),
                PidZone.CLOSE: PidZoneCoeffs(settings.PH_PID_KP_CLOSE, settings.PH_PID_KI_CLOSE, settings.PH_PID_KD_CLOSE),
                PidZone.FAR: PidZoneCoeffs(settings.PH_PID_KP_FAR, settings.PH_PID_KI_FAR, settings.PH_PID_KD_FAR),
            },
            max_output=settings.PH_PID_MAX_OUTPUT,
            min_output=0.0,
            max_integral=settings.PH_PID_MAX_INTEGRAL,
            anti_windup_mode=settings.PID_ANTI_WINDUP_MODE,
            back_calculation_gain=settings.PID_BACK_CALCULATION_GAIN,
            derivative_filter_alpha=settings.PH_PID_DERIVATIVE_FILTER_ALPHA,
            min_interval_ms=settings.PH_PID_MIN_INTERVAL_MS,
        )

    return AdaptivePidConfig(
        setpoint=setpoint,
        dead_zone=settings.EC_PID_DEAD_ZONE,
        close_zone=settings.EC_PID_CLOSE_ZONE,
        far_zone=settings.EC_PID_FAR_ZONE,
        zone_coeffs={
            PidZone.DEAD: PidZoneCoeffs(0.0, 0.0, 0.0),
            PidZone.CLOSE: PidZoneCoeffs(settings.EC_PID_KP_CLOSE, settings.EC_PID_KI_CLOSE, settings.EC_PID_KD_CLOSE),
            PidZone.FAR: PidZoneCoeffs(settings.EC_PID_KP_FAR, settings.EC_PID_KI_FAR, settings.EC_PID_KD_FAR),
        },
        max_output=settings.EC_PID_MAX_OUTPUT,
        min_output=0.0,
        max_integral=settings.EC_PID_MAX_INTEGRAL,
        anti_windup_mode=settings.PID_ANTI_WINDUP_MODE,
        back_calculation_gain=settings.PID_BACK_CALCULATION_GAIN,
        derivative_filter_alpha=settings.EC_PID_DERIVATIVE_FILTER_ALPHA,
        min_interval_ms=settings.EC_PID_MIN_INTERVAL_MS,
    )


def select_actuator_for_correction(
    controller: Any,
    correction_type: str,
    actuators: Optional[Dict[str, Dict[str, Any]]],
    nodes: Optional[Dict[str, Dict[str, Any]]],
) -> Optional[Dict[str, Any]]:
    """Выбрать actuator по роли."""
    _ = nodes
    role_order: List[str] = []
    if controller.correction_type.value == "ph":
        role_order = ["ph_base_pump"] if correction_type == "add_base" else ["ph_acid_pump"]
    elif correction_type == "add_nutrients":
        role_order = ["ec_npk_pump", "ec_calcium_pump", "ec_magnesium_pump", "ec_micro_pump"]
    elif correction_type == "dilute":
        role_order = ["recirculation_pump", "irrigation_pump", "main_pump", "pump"]
    else:
        return None

    if actuators:
        for role in role_order:
            if role in actuators:
                return actuators[role]
    return None


def build_ec_component_batch_for_controller(
    controller: Any,
    targets: Dict[str, Any],
    actuators: Optional[Dict[str, Dict[str, Any]]],
    total_ml: float,
    current_ec: float,
    target_ec: float,
    allowed_ec_components: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    return build_ec_component_batch(
        targets=targets,
        actuators=actuators,
        total_ml=total_ml,
        current_ec=current_ec,
        target_ec=target_ec,
        allowed_ec_components=allowed_ec_components,
        build_correction_command=controller._build_correction_command,
    )


def build_actuator_identity_for_controller(controller: Any, actuator: Dict[str, Any]) -> str:
    _ = controller
    return build_actuator_identity(actuator)


def resolve_ec_component_ratios_for_controller(
    controller: Any,
    targets: Dict[str, Any],
    available_components: List[str],
) -> Dict[str, float]:
    _ = controller
    return resolve_ec_component_ratios(targets, available_components)


def resolve_nutrition_mode_for_controller(controller: Any, nutrition: Dict[str, Any]) -> str:
    _ = controller
    return resolve_nutrition_mode(nutrition)


def resolve_solution_volume_l_for_controller(controller: Any, nutrition: Dict[str, Any]) -> Optional[float]:
    _ = controller
    return resolve_solution_volume_l(nutrition)


def build_correction_command_payload(
    controller: Any,
    actuator: Dict[str, Any],
    correction_type: str,
    amount_ml: float,
) -> Dict[str, Any]:
    """Собрать payload команды дозирования для actuator."""
    role = (actuator.get("role") or "").lower()
    use_dose = role.startswith("ph_")
    params: Dict[str, Any] = {"type": correction_type, "ml": amount_ml}

    if use_dose:
        cmd = "dose"
    else:
        cmd = "run_pump"
        ml_per_sec = actuator.get("ml_per_sec") or 1.0
        try:
            ml_per_sec = float(ml_per_sec)
        except (TypeError, ValueError):
            ml_per_sec = 1.0
        duration_ms = max(1, int((amount_ml / ml_per_sec) * 1000))
        params["duration_ms"] = duration_ms

    _ = controller
    return {"cmd": cmd, "params": params}


def extract_nutrition_control_for_controller(controller: Any, targets: Dict[str, Any]) -> Dict[str, Any]:
    _ = controller
    return extract_nutrition_control(targets)


def resolve_batch_dose_control_for_controller(controller: Any, command: Dict[str, Any]) -> tuple[float, float]:
    _ = controller
    return resolve_batch_dose_control(command)


async def get_latest_ec_value_for_zone(controller: Any, zone_id: int) -> Optional[float]:
    _ = controller
    return await get_latest_ec_value(zone_id, fetch_fn=fetch)


def determine_correction_type_for_diff(controller: Any, diff: float) -> str:
    """Определить тип корректировки на основе разницы."""
    is_ph = controller.correction_type.value == "ph"
    if is_ph:
        return "add_base" if diff < 0 else "add_acid"
    return "add_nutrients" if diff < 0 else "dilute"


def calculate_amount_for_diff(controller: Any, diff: float) -> float:
    """Рассчитать количество для дозирования."""
    settings = get_settings()
    if controller.correction_type.value == "ph":
        return abs(diff) * settings.PH_DOSING_MULTIPLIER
    return abs(diff) * settings.EC_DOSING_MULTIPLIER


def get_correction_event_type_for_controller(controller: Any) -> str:
    """Получить тип события для корректировки."""
    return "PH_CORRECTED" if controller.correction_type.value == "ph" else "EC_DOSING"
