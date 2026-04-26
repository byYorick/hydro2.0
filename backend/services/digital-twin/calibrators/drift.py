"""Sim2real drift monitor (Phase D / D6).

Использует `replay.replay_zone()` с `include_actual=True` для расчёта MAE
между предсказанием DT и фактической телеметрией за заданный период.
Возвращает dict per metric (ph, ec, temp_air, humidity_air) + флаг
`drift_detected` если MAE превышает threshold.

Пороги по умолчанию:
- pH:        0.20
- EC:        0.15  (mS/cm)
- temp_air:  1.5   (°C)
- humidity:  10.0  (%)

Эти значения консервативны для prod-зоны на 7-дневном horizon. При
превышении нужно запустить рекалибровку через `runner.calibrate_zone_with_persist`.
"""
import logging
from datetime import datetime
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

DEFAULT_DRIFT_THRESHOLDS: Dict[str, float] = {
    "ph": 0.20,
    "ec": 0.15,
    "temp_air": 1.5,
    "humidity_air": 10.0,
}


async def compute_drift_for_zone(
    zone_id: int,
    from_ts: datetime,
    to_ts: datetime,
    *,
    step_minutes: int = 15,
    thresholds: Optional[Dict[str, float]] = None,
) -> Dict[str, Any]:
    """Прогнать replay с include_actual=True и вернуть drift summary.

    Возвращает:
        {
            "zone_id": ..., "from_ts": ..., "to_ts": ...,
            "mae": {"ph": ..., "ec": ..., ...},
            "thresholds": {...},
            "drift_detected": bool,
            "drift_metrics": [имена метрик, перешагнувших threshold],
            "commands_replayed": int,
            "points_count": int
        }
    """
    # Локальный импорт для разрыва циклического импорта (replay → main → calibrators).
    from replay import ReplayRequest, replay_zone

    request = ReplayRequest(
        zone_id=zone_id,
        from_ts=from_ts,
        to_ts=to_ts,
        step_minutes=step_minutes,
        include_actual=True,
    )
    result = await replay_zone(request)

    mae = result.get("mae") or {}
    thresholds_eff = dict(DEFAULT_DRIFT_THRESHOLDS)
    if thresholds:
        thresholds_eff.update(
            {k: float(v) for k, v in thresholds.items() if v is not None}
        )

    drift_metrics = []
    for metric, value in mae.items():
        thr = thresholds_eff.get(metric)
        if thr is None:
            continue
        try:
            if float(value) > thr:
                drift_metrics.append(metric)
        except (TypeError, ValueError):
            continue

    return {
        "zone_id": zone_id,
        "from_ts": from_ts.isoformat(),
        "to_ts": to_ts.isoformat(),
        "step_minutes": step_minutes,
        "mae": mae,
        "thresholds": thresholds_eff,
        "drift_detected": bool(drift_metrics),
        "drift_metrics": drift_metrics,
        "commands_replayed": result.get("commands_replayed", 0),
        "points_count": len(result.get("points") or []),
    }
