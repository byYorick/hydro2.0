"""Runner — orchestrator калибровки зоны.

Запускает все доступные калибраторы и опционально сохраняет результаты в
`zone_dt_params`. Использует существующую legacy-логику pH/EC/Climate из
`calibration.py` (regression-стабильно), плюс новый TankCalibrator.
"""
import logging
from datetime import timedelta
from typing import Any, Dict, List, Optional

from common.utils.time import utcnow

# Legacy калибраторы (regression contract).
from calibration import (
    calibrate_climate_model,
    calibrate_ec_model,
    calibrate_ph_model,
)

from .storage import persist_param_group
from .tank import calibrate_tank_model

logger = logging.getLogger(__name__)


async def calibrate_zone(zone_id: int, days: int = 7) -> Dict[str, Any]:
    """Запустить все калибраторы и вернуть структурированный результат.

    Не сохраняет в БД — это делает `calibrate_zone_with_persist`.
    """
    end = utcnow()
    start = end - timedelta(days=days)
    logger.info(
        "Calibrating zone=%s, range=[%s, %s]", zone_id, start, end
    )

    ph_params = await calibrate_ph_model(zone_id, days)
    ec_params = await calibrate_ec_model(zone_id, days)
    climate_params = await calibrate_climate_model(zone_id, days)
    tank_result = await calibrate_tank_model(zone_id, days)

    return {
        "zone_id": zone_id,
        "calibrated_at": end.isoformat(),
        "data_period_days": days,
        "data_period_start": start.isoformat(),
        "data_period_end": end.isoformat(),
        "models": {
            "ph": ph_params,
            "ec": ec_params,
            "climate": climate_params,
            "tank": tank_result.params,
        },
        "n_samples_used": {
            "tank": tank_result.n_samples_used,
        },
        "notes": {
            "tank": tank_result.notes,
        },
    }


async def calibrate_zone_with_persist(
    zone_id: int,
    days: int = 7,
    *,
    calibration_mae: Optional[Dict[str, Dict[str, float]]] = None,
) -> Dict[str, Any]:
    """Прогнать калибровку и записать активные версии в `zone_dt_params`.

    `calibration_mae` — опциональный нагрузочный показатель per group, если он
    был получен извне (например, из drift_monitor).
    """
    result = await calibrate_zone(zone_id, days)
    end = utcnow()
    start = end - timedelta(days=days)

    persisted: List[Dict[str, Any]] = []
    for group, params in result["models"].items():
        if not params:
            continue
        try:
            n_used = None
            if isinstance(result.get("n_samples_used"), dict):
                n_used = result["n_samples_used"].get(group)
            mae_for_group = None
            if calibration_mae and isinstance(calibration_mae, dict):
                mae_for_group = calibration_mae.get(group)
            version = await persist_param_group(
                zone_id=zone_id,
                param_group=group,
                params=params,
                calibrated_from_start=start,
                calibrated_from_end=end,
                calibration_mae=mae_for_group,
                n_samples_used=n_used,
            )
            persisted.append({"param_group": group, "version": version})
        except Exception as exc:
            logger.warning(
                "Failed to persist param_group=%s zone=%s: %s",
                group, zone_id, exc,
            )

    result["persisted"] = persisted
    return result
