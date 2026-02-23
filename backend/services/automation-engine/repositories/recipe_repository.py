"""
Recipe Repository - доступ к рецептам и фазам.
Использует Laravel API для получения effective targets (новая модель GrowCycle).
"""
import logging
from datetime import datetime
from typing import Dict, Any, Optional, List
from common.db import create_zone_event
from common.infra_alerts import send_infra_alert, send_infra_resolved_alert
from common.utils.time import utcnow
from infrastructure.circuit_breaker import CircuitBreaker
from repositories.laravel_api_repository import LaravelApiRepository
from repositories.recipe_repository_zone_multi import load_zones_data_batch_optimized
from repositories.recipe_repository_zone_single import load_zone_data_batch
from common.effective_targets import parse_effective_targets
from services.resilience_contract import INFRA_CORRECTION_FLAGS_TELEMETRY_SAMPLES_MISSING

logger = logging.getLogger(__name__)
MISSING_TELEMETRY_SAMPLES_REPORT_THROTTLE_SECONDS = 300


def _to_optional_bool(value: Any) -> Optional[bool]:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        if value == 1:
            return True
        if value == 0:
            return False
        return None
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off"}:
            return False
    return None


class RecipeRepository:
    """Репозиторий для работы с рецептами."""
    
    def __init__(self, db_circuit_breaker: Optional[CircuitBreaker] = None):
        """
        Инициализация репозитория.
        
        Args:
            db_circuit_breaker: Circuit breaker для БД (опционально)
        """
        self.db_circuit_breaker = db_circuit_breaker
        self.laravel_api = LaravelApiRepository()
        self._telemetry_samples_missing_alert_active: Dict[int, bool] = {}
        self._telemetry_samples_missing_last_report_at: Dict[int, datetime] = {}

    @staticmethod
    def _normalize_timestamp(value: Any) -> Optional[str]:
        if value is None:
            return None
        if hasattr(value, "isoformat"):
            return value.isoformat()
        return str(value)

    async def _create_zone_event_safe(
        self,
        *,
        zone_id: int,
        event_type: str,
        details: Dict[str, Any],
    ) -> bool:
        try:
            await create_zone_event(zone_id, event_type, details)
            return True
        except Exception as event_error:
            logger.warning(
                "Zone %s: failed to persist zone event %s: %s",
                zone_id,
                event_type,
                event_error,
                exc_info=True,
            )
            return False

    async def _sync_telemetry_samples_health_signal(
        self,
        *,
        zone_id: int,
        correction_flags_raw: Optional[Dict[str, Any]],
        capabilities: Optional[Dict[str, Any]] = None,
    ) -> None:
        if not isinstance(correction_flags_raw, dict):
            return
        if isinstance(capabilities, dict):
            if not bool(capabilities.get("ph_control") or capabilities.get("ec_control")):
                return

        samples_present_raw = correction_flags_raw.get("samples_present")
        if samples_present_raw is None:
            return

        samples_present = _to_optional_bool(samples_present_raw)
        if samples_present is None:
            return

        latest_sample_ts = self._normalize_timestamp(correction_flags_raw.get("latest_sample_ts"))
        is_active = bool(self._telemetry_samples_missing_alert_active.get(zone_id, False))

        if samples_present:
            if not is_active:
                return
            resolved_sent = await send_infra_resolved_alert(
                code=INFRA_CORRECTION_FLAGS_TELEMETRY_SAMPLES_MISSING,
                alert_type="Correction Flags Telemetry Missing",
                message=f"Zone {zone_id}: telemetry_samples for correction flags restored",
                zone_id=zone_id,
                service="automation-engine",
                component="recipe_repository",
                details={
                    "zone_id": zone_id,
                    "sensor_types": ["PH", "EC"],
                    "latest_sample_ts": latest_sample_ts,
                },
            )
            if resolved_sent:
                await self._create_zone_event_safe(
                    zone_id=zone_id,
                    event_type="CORRECTION_FLAGS_SOURCE_RESTORED",
                    details={
                        "source": "telemetry_samples",
                        "sensor_types": ["PH", "EC"],
                        "latest_sample_ts": latest_sample_ts,
                    },
                )
                self._telemetry_samples_missing_alert_active[zone_id] = False
                self._telemetry_samples_missing_last_report_at.pop(zone_id, None)
            return

        now = utcnow()
        last_reported = self._telemetry_samples_missing_last_report_at.get(zone_id)
        if isinstance(last_reported, datetime) and (
            now - last_reported
        ).total_seconds() < MISSING_TELEMETRY_SAMPLES_REPORT_THROTTLE_SECONDS:
            return

        logger.warning(
            "Zone %s: telemetry_samples missing for PH/EC sensors, correction flags cannot be computed from samples metadata",
            zone_id,
            extra={"zone_id": zone_id, "latest_sample_ts": latest_sample_ts},
        )

        event_created = False
        if not is_active:
            event_created = await self._create_zone_event_safe(
                zone_id=zone_id,
                event_type="CORRECTION_FLAGS_SOURCE_MISSING",
                details={
                    "source": "telemetry_samples",
                    "sensor_types": ["PH", "EC"],
                    "latest_sample_ts": latest_sample_ts,
                    "reason": "samples_absent_for_ph_ec",
                },
            )

        alert_sent = await send_infra_alert(
            code=INFRA_CORRECTION_FLAGS_TELEMETRY_SAMPLES_MISSING,
            alert_type="Correction Flags Telemetry Missing",
            message=f"Zone {zone_id}: telemetry_samples missing for PH/EC, correction flags degraded",
            severity="error",
            zone_id=zone_id,
            service="automation-engine",
            component="recipe_repository",
            error_type="TelemetrySamplesMissing",
            details={
                "zone_id": zone_id,
                "sensor_types": ["PH", "EC"],
                "latest_sample_ts": latest_sample_ts,
                "throttle_seconds": MISSING_TELEMETRY_SAMPLES_REPORT_THROTTLE_SECONDS,
            },
        )
        if alert_sent or event_created:
            self._telemetry_samples_missing_alert_active[zone_id] = True
            self._telemetry_samples_missing_last_report_at[zone_id] = now

    @staticmethod
    def _extract_correction_flags(
        correction_flags_raw: Optional[Dict[str, Any]],
        telemetry: Dict[str, Optional[float]],
        telemetry_timestamps: Dict[str, Any],
    ) -> Dict[str, Any]:
        raw_flags = correction_flags_raw if isinstance(correction_flags_raw, dict) else {}
        flow_active = _to_optional_bool(raw_flags.get("flow_active"))
        if flow_active is None:
            flow_active = _to_optional_bool(telemetry.get("FLOW_ACTIVE"))
        stable = _to_optional_bool(raw_flags.get("stable"))
        if stable is None:
            stable = _to_optional_bool(telemetry.get("STABLE"))
        corrections_allowed = _to_optional_bool(raw_flags.get("corrections_allowed"))
        if corrections_allowed is None:
            corrections_allowed = _to_optional_bool(telemetry.get("CORRECTIONS_ALLOWED"))
        return {
            "flow_active": flow_active,
            "stable": stable,
            "corrections_allowed": corrections_allowed,
            "flow_active_ts": raw_flags.get("flow_active_ts", telemetry_timestamps.get("FLOW_ACTIVE")),
            "stable_ts": raw_flags.get("stable_ts", telemetry_timestamps.get("STABLE")),
            "corrections_allowed_ts": raw_flags.get(
                "corrections_allowed_ts",
                telemetry_timestamps.get("CORRECTIONS_ALLOWED"),
            ),
        }
    
    async def get_zone_recipe_and_targets(self, zone_id: int) -> Optional[Dict[str, Any]]:
        """
        Получить активный рецепт и targets для зоны (новая модель через Laravel API).
        
        Args:
            zone_id: ID зоны
        
        Returns:
            Dict с zone_id, phase_index, targets, phase_name или None
        
        Raises:
            CircuitBreakerOpenError: Если Circuit Breaker открыт
        """
        # Используем Laravel API для получения effective targets
        try:
            effective_targets = await self.laravel_api.get_effective_targets(zone_id)
            if not effective_targets:
                return None
            try:
                parsed = parse_effective_targets(effective_targets)
            except Exception as e:
                logger.warning(f'Failed to parse effective targets for zone {zone_id}: {e}')
                return None

            normalized = parsed.model_dump()
            # Преобразуем формат из Laravel API в формат, ожидаемый кодом
            phase = normalized.get('phase', {})
            targets = normalized.get('targets', {})

            return {
                "zone_id": normalized.get('zone_id', zone_id),
                "cycle_id": normalized.get('cycle_id'),
                "phase_index": phase.get('id'),  # Используем ID фазы как индекс
                "targets": targets,
                "phase_name": phase.get('name', phase.get('code', 'UNKNOWN')),
            }
        except Exception as e:
            logger.warning(f'Failed to get effective targets from Laravel API for zone {zone_id}: {e}')
            return None
    
    async def get_zones_recipes_batch(self, zone_ids: List[int]) -> Dict[int, Optional[Dict[str, Any]]]:
        """
        Получить рецепты и targets для нескольких зон одним запросом (новая модель через Laravel API).
        
        Args:
            zone_ids: Список ID зон
        
        Returns:
            Dict[zone_id, recipe_info] или None если рецепта нет
        
        Raises:
            CircuitBreakerOpenError: Если Circuit Breaker открыт
        """
        if not zone_ids:
            return {}
        
        try:
            effective_targets_batch = await self.laravel_api.get_effective_targets_batch(zone_ids)

            # Преобразуем формат из Laravel API в формат, ожидаемый кодом
            result: Dict[int, Optional[Dict[str, Any]]] = {}
            for zone_id in zone_ids:
                effective_targets = effective_targets_batch.get(zone_id)
                if not effective_targets or 'error' in effective_targets:
                    result[zone_id] = None
                    continue

                try:
                    parsed = parse_effective_targets(effective_targets)
                    normalized = parsed.model_dump()
                except Exception as e:
                    logger.warning(f'Failed to parse effective targets for zone {zone_id}: {e}')
                    result[zone_id] = None
                    continue

                phase = normalized.get('phase', {})
                targets = normalized.get('targets', {})

                result[zone_id] = {
                    "zone_id": normalized.get('zone_id', zone_id),
                    "cycle_id": normalized.get('cycle_id'),
                    "phase_index": phase.get('id'),  # Используем ID фазы как индекс
                    "targets": targets,
                    "phase_name": phase.get('name', phase.get('code', 'UNKNOWN')),
                }

            return result
        except Exception as e:
            logger.warning(f'Failed to get effective targets batch from Laravel API: {e}')
            return {zone_id: None for zone_id in zone_ids}
    
    async def get_zone_data_batch(self, zone_id: int) -> Dict[str, Any]:
        """
        Получить данные зоны одним запросом (telemetry, nodes, capabilities).
        Targets и recipe_info здесь больше не подгружаются.
        
        Args:
            zone_id: ID зоны
        
        Returns:
            Dict с recipe_info (None), telemetry, nodes, capabilities
        
        Raises:
            CircuitBreakerOpenError: Если Circuit Breaker открыт
        """
        return await load_zone_data_batch(self, zone_id)

    async def get_zones_data_batch_optimized(self, zone_ids: List[int]) -> Dict[int, Dict[str, Any]]:
        """
        Оптимизированный batch запрос для получения данных нескольких зон одним запросом.
        Targets и recipe_info здесь больше не подгружаются.
        
        Args:
            zone_ids: Список ID зон
        
        Returns:
            Dict[zone_id, zone_data] с полными данными каждой зоны
        
        Raises:
            CircuitBreakerOpenError: Если Circuit Breaker открыт
        """
        return await load_zones_data_batch_optimized(self, zone_ids)
