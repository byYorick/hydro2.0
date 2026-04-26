"""Persist калиброванных параметров в `zone_dt_params`.

Контракт миграции `2026_04_25_120000_create_zone_dt_params_table.php`:
- (zone_id, param_group, version) UNIQUE
- `superseded_at` IS NULL для активной версии
- `calibrated_from_start/end` — диапазон данных, на которых обучались

При записи новой версии:
1. Получить max(version) для (zone_id, param_group).
2. Вытеснить активную (superseded_at = NOW()).
3. INSERT новой строки с version+1.
"""
import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from common.db import execute, fetch
from common.utils.time import utcnow

logger = logging.getLogger(__name__)

PARAM_GROUPS = ("tank", "ph", "ec", "climate", "substrate", "uptake", "actuator")


async def persist_param_group(
    zone_id: int,
    param_group: str,
    params: Dict[str, float],
    *,
    calibrated_from_start: datetime,
    calibrated_from_end: datetime,
    calibration_mae: Optional[Dict[str, float]] = None,
    n_samples_used: Optional[int] = None,
) -> int:
    """Записать новую версию параметров для зоны/группы.

    Возвращает version новой строки.
    """
    if param_group not in PARAM_GROUPS:
        raise ValueError(f"unknown param_group: {param_group}")
    if not isinstance(params, dict) or not params:
        raise ValueError("params must be non-empty dict")

    # Найти текущую активную версию.
    active = await fetch(
        """
        SELECT id, version
        FROM zone_dt_params
        WHERE zone_id = $1 AND param_group = $2 AND superseded_at IS NULL
        ORDER BY version DESC
        LIMIT 1
        """,
        zone_id,
        param_group,
    )
    next_version = 1
    if active:
        next_version = int(active[0]["version"]) + 1
        await execute(
            """
            UPDATE zone_dt_params
            SET superseded_at = NOW(), updated_at = NOW()
            WHERE id = $1
            """,
            active[0]["id"],
        )

    await execute(
        """
        INSERT INTO zone_dt_params
            (zone_id, param_group, params, calibrated_at,
             calibrated_from_start, calibrated_from_end,
             calibration_mae, n_samples_used, version,
             superseded_at, created_at, updated_at)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, NULL, NOW(), NOW())
        """,
        zone_id,
        param_group,
        json.dumps(_clean_params(params)),
        utcnow(),
        calibrated_from_start,
        calibrated_from_end,
        json.dumps(calibration_mae) if calibration_mae else None,
        n_samples_used,
        next_version,
    )
    logger.info(
        "Persisted dt_params zone=%s group=%s version=%s",
        zone_id, param_group, next_version,
    )
    return next_version


async def list_active_params(zone_id: int) -> Dict[str, Dict[str, float]]:
    """Считать все активные группы параметров для зоны."""
    rows = await fetch(
        """
        SELECT param_group, params, version, calibrated_at, calibration_mae, n_samples_used
        FROM zone_dt_params
        WHERE zone_id = $1 AND superseded_at IS NULL
        """,
        zone_id,
    )
    out: Dict[str, Dict[str, Any]] = {}
    for row in rows or []:
        params = row.get("params") or {}
        if isinstance(params, str):
            try:
                params = json.loads(params)
            except json.JSONDecodeError:
                continue
        if not isinstance(params, dict):
            continue
        mae = row.get("calibration_mae")
        if isinstance(mae, str):
            try:
                mae = json.loads(mae)
            except json.JSONDecodeError:
                mae = None
        out[str(row["param_group"])] = {
            "params": _clean_params(params),
            "version": int(row["version"]),
            "calibrated_at": (
                row["calibrated_at"].isoformat() if row.get("calibrated_at") else None
            ),
            "calibration_mae": mae,
            "n_samples_used": row.get("n_samples_used"),
        }
    return out


async def list_versions(zone_id: int, param_group: str) -> List[Dict[str, Any]]:
    """История всех версий конкретной группы."""
    rows = await fetch(
        """
        SELECT version, calibrated_at, superseded_at, calibration_mae, n_samples_used
        FROM zone_dt_params
        WHERE zone_id = $1 AND param_group = $2
        ORDER BY version DESC
        """,
        zone_id,
        param_group,
    )
    out: List[Dict[str, Any]] = []
    for row in rows or []:
        mae = row.get("calibration_mae")
        if isinstance(mae, str):
            try:
                mae = json.loads(mae)
            except json.JSONDecodeError:
                mae = None
        out.append({
            "version": int(row["version"]),
            "calibrated_at": row["calibrated_at"].isoformat() if row.get("calibrated_at") else None,
            "superseded_at": row["superseded_at"].isoformat() if row.get("superseded_at") else None,
            "calibration_mae": mae,
            "n_samples_used": row.get("n_samples_used"),
        })
    return out


# --- helpers --------------------------------------------------------------


def _clean_params(params: Dict[str, Any]) -> Dict[str, float]:
    cleaned: Dict[str, float] = {}
    for key, value in params.items():
        if value is None:
            continue
        try:
            cleaned[str(key)] = float(value)
        except (TypeError, ValueError):
            continue
    return cleaned
