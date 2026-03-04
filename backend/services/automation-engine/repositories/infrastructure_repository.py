"""
Infrastructure Repository - доступ к инфраструктуре зон и bindings.
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set, Tuple
import logging

from prometheus_client import Gauge

from common.db import fetch
from infrastructure.circuit_breaker import CircuitBreaker, CircuitBreakerOpenError

logger = logging.getLogger(__name__)
CALIBRATION_STALENESS_HOURS = Gauge(
    "calibration_staleness_hours",
    "Age of active pump calibration used by automation-engine",
    ["zone_id", "role"],
)


class InfrastructureRepository:
    """Репозиторий для работы с инфраструктурой зон и bindings."""

    def __init__(self, db_circuit_breaker: Optional[CircuitBreaker] = None):
        self.db_circuit_breaker = db_circuit_breaker
        self._multi_role_logged: Set[Tuple[int, str]] = set()

    async def get_zone_bindings_by_role(self, zone_id: int) -> Dict[str, Dict[str, Any]]:
        async def _fetch():
            return await fetch(
                """
                SELECT
                    cb.role,
                    cb.direction,
                    ii.id as asset_id,
                    ii.asset_type,
                    n.id as node_id,
                    n.uid as node_uid,
                    nc.id as node_channel_id,
                    nc.channel as channel,
                    nc.config as channel_config,
                    pc.ml_per_sec as calibration_ml_per_sec,
                    pc.k_ms_per_ml_l as calibration_k_ms_per_ml_l,
                    pc.component as calibration_component,
                    pc.source as calibration_source,
                    pc.quality_score as calibration_quality_score,
                    pc.sample_count as calibration_sample_count,
                    pc.valid_from as calibration_valid_from
                FROM infrastructure_instances ii
                JOIN channel_bindings cb ON cb.infrastructure_instance_id = ii.id
                JOIN node_channels nc ON nc.id = cb.node_channel_id
                JOIN nodes n ON n.id = nc.node_id
                LEFT JOIN LATERAL (
                    SELECT
                        p.ml_per_sec,
                        p.k_ms_per_ml_l,
                        p.component,
                        p.source,
                        p.quality_score,
                        p.sample_count,
                        p.valid_from
                    FROM pump_calibrations p
                    WHERE p.node_channel_id = nc.id
                      AND p.is_active = TRUE
                      AND p.valid_from <= NOW()
                      AND (p.valid_to IS NULL OR p.valid_to > NOW())
                    ORDER BY p.valid_from DESC, p.id DESC
                    LIMIT 1
                ) pc ON TRUE
                WHERE (
                    (ii.owner_type = 'zone' AND ii.owner_id = $1)
                    OR (
                        ii.owner_type = 'greenhouse'
                        AND ii.owner_id = (SELECT greenhouse_id FROM zones WHERE id = $1)
                    )
                )
                AND n.zone_id = $1
                AND n.status = 'online'
                AND COALESCE(nc.is_active, TRUE) = TRUE
                """,
                zone_id,
            )

        rows = await self.db_circuit_breaker.call(_fetch) if self.db_circuit_breaker else await _fetch()

        result: Dict[str, Dict[str, Any]] = {}
        for row in rows:
            role = row["role"]
            pump_calibration = self._extract_pump_calibration(row=row)
            self._observe_calibration_staleness(zone_id=zone_id, role=role, calibration=pump_calibration)

            if role not in result:
                result[role] = {
                    "zone_id": zone_id,
                    "node_id": row["node_id"],
                    "node_uid": row["node_uid"],
                    "node_channel_id": row["node_channel_id"],
                    "channel": row["channel"],
                    "asset_id": row["asset_id"],
                    "asset_type": row["asset_type"],
                    "direction": row["direction"],
                    "ml_per_sec": pump_calibration.get("ml_per_sec"),
                    "k_ms_per_ml_l": pump_calibration.get("k_ms_per_ml_l"),
                    "pump_calibration": pump_calibration,
                    "calibration_source": pump_calibration.get("source"),
                    "calibration_valid_from": pump_calibration.get("valid_from"),
                }
                self._warn_if_calibration_stale(zone_id=zone_id, actuator=result[role])
            else:
                key = (zone_id, role)
                if key not in self._multi_role_logged:
                    self._multi_role_logged.add(key)
                    logger.warning(
                        "Multiple bindings found for role; using first binding",
                        extra={"zone_id": zone_id, "role": role},
                    )

        return result

    async def get_zones_bindings_batch(self, zone_ids: List[int]) -> Dict[int, Dict[str, Dict[str, Any]]]:
        if not zone_ids:
            return {}

        async def _fetch():
            return await fetch(
                """
                SELECT
                    z.id as zone_id,
                    cb.role,
                    cb.direction,
                    ii.id as asset_id,
                    ii.asset_type,
                    n.id as node_id,
                    n.uid as node_uid,
                    nc.id as node_channel_id,
                    nc.channel as channel,
                    nc.config as channel_config,
                    pc.ml_per_sec as calibration_ml_per_sec,
                    pc.k_ms_per_ml_l as calibration_k_ms_per_ml_l,
                    pc.component as calibration_component,
                    pc.source as calibration_source,
                    pc.quality_score as calibration_quality_score,
                    pc.sample_count as calibration_sample_count,
                    pc.valid_from as calibration_valid_from
                FROM infrastructure_instances ii
                JOIN channel_bindings cb ON cb.infrastructure_instance_id = ii.id
                JOIN node_channels nc ON nc.id = cb.node_channel_id
                JOIN nodes n ON n.id = nc.node_id
                JOIN zones z ON (
                    (ii.owner_type = 'zone' AND ii.owner_id = z.id)
                    OR (ii.owner_type = 'greenhouse' AND ii.owner_id = z.greenhouse_id)
                )
                LEFT JOIN LATERAL (
                    SELECT
                        p.ml_per_sec,
                        p.k_ms_per_ml_l,
                        p.component,
                        p.source,
                        p.quality_score,
                        p.sample_count,
                        p.valid_from
                    FROM pump_calibrations p
                    WHERE p.node_channel_id = nc.id
                      AND p.is_active = TRUE
                      AND p.valid_from <= NOW()
                      AND (p.valid_to IS NULL OR p.valid_to > NOW())
                    ORDER BY p.valid_from DESC, p.id DESC
                    LIMIT 1
                ) pc ON TRUE
                WHERE z.id = ANY($1::int[])
                    AND n.zone_id = z.id
                    AND n.status = 'online'
                    AND COALESCE(nc.is_active, TRUE) = TRUE
                """,
                zone_ids,
            )

        rows = await self.db_circuit_breaker.call(_fetch) if self.db_circuit_breaker else await _fetch()

        result: Dict[int, Dict[str, Dict[str, Any]]] = {}
        for row in rows:
            zone_id = row["zone_id"]
            role = row["role"]
            pump_calibration = self._extract_pump_calibration(row=row)
            self._observe_calibration_staleness(zone_id=zone_id, role=role, calibration=pump_calibration)

            if zone_id not in result:
                result[zone_id] = {}

            if role not in result[zone_id]:
                result[zone_id][role] = {
                    "zone_id": zone_id,
                    "node_id": row["node_id"],
                    "node_uid": row["node_uid"],
                    "node_channel_id": row["node_channel_id"],
                    "channel": row["channel"],
                    "asset_id": row["asset_id"],
                    "asset_type": row["asset_type"],
                    "direction": row["direction"],
                    "ml_per_sec": pump_calibration.get("ml_per_sec"),
                    "k_ms_per_ml_l": pump_calibration.get("k_ms_per_ml_l"),
                    "pump_calibration": pump_calibration,
                    "calibration_source": pump_calibration.get("source"),
                    "calibration_valid_from": pump_calibration.get("valid_from"),
                }
                self._warn_if_calibration_stale(zone_id=zone_id, actuator=result[zone_id][role])
            else:
                key = (zone_id, role)
                if key not in self._multi_role_logged:
                    self._multi_role_logged.add(key)
                    logger.warning(
                        "Multiple bindings found for role; using first binding",
                        extra={"zone_id": zone_id, "role": role},
                    )

        for zone_id in zone_ids:
            if zone_id not in result:
                result[zone_id] = {}

        return result

    async def get_zone_asset_instances(self, zone_id: int) -> List[Dict[str, Any]]:
        async def _fetch():
            return await fetch(
                """
                SELECT
                    ii.id,
                    ii.owner_type,
                    ii.owner_id,
                    ii.asset_type,
                    ii.label,
                    ii.required,
                    ii.capacity_liters,
                    ii.flow_rate,
                    ii.specs
                FROM infrastructure_instances ii
                WHERE (
                    (ii.owner_type = 'zone' AND ii.owner_id = $1)
                    OR (
                        ii.owner_type = 'greenhouse'
                        AND ii.owner_id = (SELECT greenhouse_id FROM zones WHERE id = $1)
                    )
                )
                ORDER BY ii.asset_type, ii.label
                """,
                zone_id,
            )

        rows = await self.db_circuit_breaker.call(_fetch) if self.db_circuit_breaker else await _fetch()

        return [
            {
                "id": row["id"],
                "owner_type": row["owner_type"],
                "owner_id": row["owner_id"],
                "asset_type": row["asset_type"],
                "label": row["label"],
                "required": row["required"],
                "capacity_liters": row["capacity_liters"],
                "flow_rate": row["flow_rate"],
                "specs": row["specs"],
            }
            for row in rows
        ]

    @staticmethod
    def _extract_pump_calibration(*, row: Dict[str, Any]) -> Dict[str, Optional[float]]:
        table_ml = InfrastructureRepository._extract_positive_float(row.get("calibration_ml_per_sec"))
        table_k = InfrastructureRepository._extract_positive_float(row.get("calibration_k_ms_per_ml_l"))
        if table_ml is not None:
            return {
                "ml_per_sec": table_ml,
                "k_ms_per_ml_l": table_k,
                "component": row.get("calibration_component"),
                "source": row.get("calibration_source"),
                "quality_score": row.get("calibration_quality_score"),
                "sample_count": row.get("calibration_sample_count"),
                "valid_from": row.get("calibration_valid_from"),
            }

        channel_config = row.get("channel_config")
        if not isinstance(channel_config, dict):
            return {
                "ml_per_sec": None,
                "k_ms_per_ml_l": None,
                "component": None,
                "source": "legacy_config_fallback",
                "quality_score": None,
                "sample_count": None,
                "valid_from": None,
            }

        calibration = channel_config.get("pump_calibration")
        if not isinstance(calibration, dict):
            return {
                "ml_per_sec": None,
                "k_ms_per_ml_l": None,
                "component": None,
                "source": "legacy_config_fallback",
                "quality_score": None,
                "sample_count": None,
                "valid_from": None,
            }

        return {
            "ml_per_sec": InfrastructureRepository._extract_positive_float(calibration.get("ml_per_sec")),
            "k_ms_per_ml_l": InfrastructureRepository._extract_positive_float(calibration.get("k_ms_per_ml_l")),
            "component": calibration.get("component"),
            "source": "legacy_config_fallback",
            "quality_score": None,
            "sample_count": None,
            "valid_from": calibration.get("calibrated_at"),
        }

    @staticmethod
    def _extract_positive_float(value: Any) -> Optional[float]:
        try:
            parsed = float(value)
        except (TypeError, ValueError):
            return None
        if parsed <= 0:
            return None
        return parsed

    @staticmethod
    def _parse_calibration_ts(raw: Any) -> Optional[datetime]:
        if isinstance(raw, datetime):
            if raw.tzinfo is None:
                return raw.replace(tzinfo=timezone.utc)
            return raw.astimezone(timezone.utc)
        if isinstance(raw, str) and raw.strip():
            candidate = raw.strip().replace("Z", "+00:00")
            try:
                parsed = datetime.fromisoformat(candidate)
            except ValueError:
                return None
            if parsed.tzinfo is None:
                return parsed.replace(tzinfo=timezone.utc)
            return parsed.astimezone(timezone.utc)
        return None

    def _observe_calibration_staleness(self, *, zone_id: int, role: str, calibration: Dict[str, Any]) -> None:
        parsed = self._parse_calibration_ts(calibration.get("valid_from"))
        if parsed is None:
            return
        staleness_hours = max(0.0, (datetime.now(timezone.utc) - parsed).total_seconds() / 3600.0)
        CALIBRATION_STALENESS_HOURS.labels(zone_id=str(zone_id), role=str(role or "unknown")).set(staleness_hours)

    def _warn_if_calibration_stale(self, *, zone_id: int, actuator: Dict[str, Any]) -> None:
        valid_from = actuator.get("calibration_valid_from")
        if valid_from is None:
            calibration = actuator.get("pump_calibration")
            if isinstance(calibration, dict):
                valid_from = calibration.get("valid_from")
        parsed = self._parse_calibration_ts(valid_from)
        if parsed is None:
            return
        age_days = int(max(0.0, (datetime.now(timezone.utc) - parsed).total_seconds()) // 86400)
        if age_days > 30:
            logger.warning(
                "Pump calibration is stale: zone_id=%s, role=%s, age_days=%d",
                zone_id,
                actuator.get("role"),
                age_days,
                extra={
                    "zone_id": zone_id,
                    "role": actuator.get("role"),
                    "calibration_age_days": age_days,
                    "valid_from": str(valid_from),
                },
            )
