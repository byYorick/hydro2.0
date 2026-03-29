"""
Water Flow Engine - контроль уровня воды, расхода и защита от сухого хода.
Согласно WATER_FLOW_ENGINE.md
"""
import json
import os
from typing import Optional, Dict, Any, Tuple
from datetime import datetime
from .utils.time import utcnow
from .db import fetch, create_zone_event
from .alerts import create_alert, AlertSource, AlertCode


# Пороги для контроля воды
WATER_LEVEL_LOW_THRESHOLD = 0.2  # 20% - низкий уровень
MIN_FLOW_THRESHOLD = 0.1  # L/min - минимальный поток для обнаружения работы насоса
DRY_RUN_CHECK_DELAY_SEC = 3  # Задержка перед проверкой flow после запуска насоса


_IRRIGATION_ACTIVE_PHASES = {"irrig_recirc", "irrigating"}

_SYSTEM_AUTOMATION_CONFIG_FALLBACKS: Dict[str, Dict[str, Any]] = {
    "pump_calibration": {
        "ml_per_sec_min": 0.01,
        "ml_per_sec_max": 20.0,
        "min_dose_ms": 50,
        "calibration_duration_min_sec": 1,
        "calibration_duration_max_sec": 120,
        "quality_score_basic": 0.75,
        "quality_score_with_k": 0.90,
        "quality_score_legacy": 0.50,
        "age_warning_days": 30,
        "age_critical_days": 90,
        "default_run_duration_sec": 20,
    },
}

import logging as _logging
_wf_logger = _logging.getLogger(__name__)


async def _load_system_authority_policy(namespace: str) -> Dict[str, Any]:
    authority_namespace = {
        "pump_calibration": "system.pump_calibration_policy",
    }.get(namespace)

    if authority_namespace is None:
        raise RuntimeError(f"unsupported system authority namespace '{namespace}'")

    rows = await fetch(
        """
        SELECT payload
        FROM automation_config_documents
        WHERE namespace = $1
          AND scope_type = 'system'
          AND scope_id = 0
        LIMIT 1
        """,
        authority_namespace,
    )
    if not rows:
        fallback = _SYSTEM_AUTOMATION_CONFIG_FALLBACKS.get(namespace)
        if fallback is None:
            raise RuntimeError(f"system authority namespace '{namespace}' not found")

        _wf_logger.warning(
            "system authority namespace '%s' not found; using built-in fallback",
            namespace,
        )
        return dict(fallback)

    config = rows[0]["payload"]
    return json.loads(config) if isinstance(config, str) else dict(config)


async def check_water_level(
    zone_id: int,
    *,
    workflow_phase: Optional[str] = None,
) -> Tuple[bool, Optional[float]]:
    """
    Проверка уровня воды в зоне.

    Args:
        zone_id: ID зоны
        workflow_phase: Текущая фаза workflow (опционально). Если фаза ирригации
            и все датчики читают ровно 0.0, считаем уровень нормальным —
            это артефакт перезагрузки ноды (бинарные датчики не успели отправить данные).

    Returns:
        (is_ok, level_value): True если уровень нормальный (>= 0.2), False если низкий
    """
    rows = await fetch(
        """
        SELECT
          tl.last_value as value
        FROM telemetry_last tl
        JOIN sensors s ON s.id = tl.sensor_id
        WHERE s.zone_id = $1
          AND s.type = 'WATER_LEVEL'
          AND s.is_active = TRUE
        ORDER BY
          CASE
            WHEN LOWER(COALESCE(s.label, '')) LIKE '%clean%' THEN 0
            WHEN LOWER(COALESCE(s.label, '')) LIKE '%fresh%' THEN 0
            WHEN LOWER(COALESCE(s.label, '')) LIKE '%чист%' THEN 0
            WHEN LOWER(COALESCE(s.label, '')) LIKE '%solution%' THEN 1
            WHEN LOWER(COALESCE(s.label, '')) LIKE '%mix%' THEN 1
            WHEN LOWER(COALESCE(s.label, '')) LIKE '%раствор%' THEN 1
            WHEN LOWER(COALESCE(s.label, '')) LIKE '%drain%' THEN 2
            WHEN LOWER(COALESCE(s.label, '')) LIKE '%waste%' THEN 2
            WHEN LOWER(COALESCE(s.label, '')) LIKE '%слив%' THEN 2
            ELSE 1
          END ASC,
          CASE
            WHEN LOWER(COALESCE(s.label, '')) LIKE '%min%' THEN 0
            WHEN LOWER(COALESCE(s.label, '')) LIKE '%макс%' THEN 2
            WHEN LOWER(COALESCE(s.label, '')) LIKE '%max%' THEN 2
            ELSE 1
          END ASC,
          tl.last_ts DESC NULLS LAST,
          tl.updated_at DESC NULLS LAST,
          tl.sensor_id DESC
        LIMIT 1
        """,
        zone_id,
    )

    if not rows or rows[0]["value"] is None:
        return True, None

    level = float(rows[0]["value"])
    is_ok = level >= WATER_LEVEL_LOW_THRESHOLD

    if not is_ok and level == 0.0 and workflow_phase in _IRRIGATION_ACTIVE_PHASES:
        _wf_logger.warning(
            "check_water_level: zone %s — water_level=0.0 in active irrigation phase '%s', "
            "likely node reboot artifact — bypassing level check",
            zone_id,
            workflow_phase,
        )
        return True, level

    return is_ok, level


async def check_flow(zone_id: int, min_flow: float = MIN_FLOW_THRESHOLD) -> Tuple[bool, Optional[float]]:
    """
    Проверка расхода воды в зоне.
    """
    rows = await fetch(
        """
        SELECT tl.last_value as value
        FROM telemetry_last tl
        JOIN sensors s ON s.id = tl.sensor_id
        WHERE s.zone_id = $1
          AND s.type = 'FLOW_RATE'
          AND s.is_active = TRUE
        ORDER BY tl.last_ts DESC NULLS LAST,
          tl.updated_at DESC NULLS LAST,
          tl.sensor_id DESC
        LIMIT 1
        """,
        zone_id,
    )

    if not rows or rows[0]["value"] is None:
        return False, None

    flow = float(rows[0]["value"])
    is_ok = flow >= min_flow

    return is_ok, flow


async def check_dry_run_protection(
    zone_id: int,
    pump_start_time: datetime,
    min_flow: float = MIN_FLOW_THRESHOLD
) -> Tuple[bool, Optional[str]]:
    """
    Защита от сухого хода насоса.
    """
    now = utcnow()
    elapsed_sec = (now - pump_start_time).total_seconds()

    if elapsed_sec < DRY_RUN_CHECK_DELAY_SEC:
        return True, None

    flow_ok, flow_value = await check_flow(zone_id, min_flow)

    if not flow_ok:
        await create_zone_event(
            zone_id,
            'NO_FLOW',
            {
                'pump_start_time': pump_start_time.isoformat(),
                'elapsed_sec': elapsed_sec,
                'flow_value': flow_value,
                'min_flow_threshold': min_flow
            }
        )
        return False, f"NO_FLOW detected: flow={flow_value} L/min < {min_flow} L/min after {elapsed_sec:.1f}s"

    return True, None


async def calculate_irrigation_volume(
    zone_id: int,
    start_time: datetime,
    end_time: datetime
) -> float:
    """
    Расчет объема полива на основе flow за период времени.
    """
    rows = await fetch(
        """
        SELECT ts.value, ts.ts
        FROM telemetry_samples ts
        JOIN sensors s ON s.id = ts.sensor_id
        WHERE ts.zone_id = $1
          AND s.type = 'FLOW_RATE'
          AND ts.ts >= $2
          AND ts.ts <= $3
        ORDER BY ts.ts ASC
        """,
        zone_id,
        start_time,
        end_time,
    )

    if not rows or len(rows) < 2:
        return 0.0

    total_volume = 0.0
    for i in range(len(rows) - 1):
        flow1 = float(rows[i]["value"]) if rows[i]["value"] is not None else 0.0
        time1 = rows[i]["ts"]
        flow2 = float(rows[i + 1]["value"]) if rows[i + 1]["value"] is not None else 0.0
        time2 = rows[i + 1]["ts"]

        avg_flow = (flow1 + flow2) / 2.0
        dt_sec = (time2 - time1).total_seconds()
        volume_segment = avg_flow * (dt_sec / 60.0)
        total_volume += volume_segment

    return total_volume


async def ensure_water_level_alert(zone_id: int, level: float) -> None:
    """
    Создание/обновление алерта WATER_LEVEL_LOW если уровень низкий.
    """
    if level < WATER_LEVEL_LOW_THRESHOLD:
        await create_alert(
            zone_id=zone_id,
            source=AlertSource.BIZ.value,
            code=AlertCode.BIZ_DRY_RUN.value,
            type='Water level low',
            details={'level': level, 'threshold': WATER_LEVEL_LOW_THRESHOLD}
        )
        await create_zone_event(
            zone_id,
            'WATER_LEVEL_LOW',
            {
                'level': level,
                'threshold': WATER_LEVEL_LOW_THRESHOLD
            }
        )


async def ensure_no_flow_alert(zone_id: int, flow_value: Optional[float], min_flow: float) -> None:
    """
    Создание/обновление алерта NO_FLOW если расход отсутствует.
    """
    if flow_value is None or flow_value < min_flow:
        await create_alert(
            zone_id=zone_id,
            source=AlertSource.BIZ.value,
            code=AlertCode.BIZ_NO_FLOW.value,
            type='No water flow detected',
            details={
                'flow_value': flow_value,
                'min_flow': min_flow
            }
        )
