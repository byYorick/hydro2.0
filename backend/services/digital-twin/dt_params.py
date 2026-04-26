"""Чтение активных параметров `zone_dt_params` для DT.

Вынесено из main.py чтобы избежать `Duplicated timeseries`-конфликта в
prometheus_client при повторном импорте `main` модуля (когда supervisor
запускает main.py как script, а другие модули импортируют его через
`from main import get_zone_dt_params`).
"""
import json
import logging
from decimal import Decimal
from typing import Dict

from common.db import fetch

logger = logging.getLogger(__name__)


async def get_zone_dt_params(zone_id: int) -> Dict[str, Dict[str, float]]:
    """Считать активные (не вытесненные) параметры моделей DT для зоны.

    Возвращает map `param_group -> {param_name: float}`. Группы, описанные
    в `zone_dt_params` (tank/ph/ec/climate/substrate/uptake/actuator), будут
    переданы в соответствующие solver-ы через ZoneWorld; недостающие группы
    остаются на defaults.
    """
    try:
        rows = await fetch(
            """
            SELECT param_group, params
            FROM zone_dt_params
            WHERE zone_id = $1 AND superseded_at IS NULL
            """,
            zone_id,
        )
    except Exception as exc:
        logger.warning(
            "Failed to load zone_dt_params for zone %s: %s. Using defaults.",
            zone_id,
            exc,
        )
        return {}

    out: Dict[str, Dict[str, float]] = {}
    for row in rows:
        group = str(row.get("param_group") or "").strip()
        params_value = row.get("params")
        if isinstance(params_value, str):
            try:
                params_value = json.loads(params_value)
            except json.JSONDecodeError:
                continue
        if not group or not isinstance(params_value, dict):
            continue
        cleaned: Dict[str, float] = {}
        for key, value in params_value.items():
            if value is None:
                continue
            if isinstance(value, Decimal):
                cleaned[str(key)] = float(value)
                continue
            try:
                cleaned[str(key)] = float(value)
            except (TypeError, ValueError):
                continue
        if cleaned:
            out[group] = cleaned
    return out
