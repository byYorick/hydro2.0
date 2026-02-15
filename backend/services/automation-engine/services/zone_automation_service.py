"""
Zone Automation Service - оркестрация обработки зоны.
Изолирует бизнес-логику от инфраструктуры.
"""
from typing import Dict, Any, Optional, List
import logging
from datetime import datetime, timedelta
import inspect
from common.utils.time import utcnow
from common.simulation_clock import SimulationClock
from common.simulation_events import record_simulation_event
from common.infra_alerts import (
    send_infra_alert,
    send_infra_exception_alert,
    send_infra_resolved_alert,
)
from common.db import create_zone_event
from common.water_flow import check_water_level, ensure_water_level_alert
from common.pump_safety import can_run_pump
# from recipe_utils import calculate_current_phase, advance_phase  # DEPRECATED - legacy functions removed
from light_controller import check_and_control_lighting
from climate_controller import check_and_control_climate
from irrigation_controller import check_and_control_irrigation, check_and_control_recirculation
from health_monitor import calculate_zone_health, update_zone_health_in_db
from correction_controller import CorrectionController, CorrectionType
from repositories import (
    ZoneRepository, 
    TelemetryRepository, 
    NodeRepository, 
    RecipeRepository,
    GrowCycleRepository,
    InfrastructureRepository
)
from infrastructure.command_bus import CommandBus
from infrastructure.circuit_breaker import CircuitBreakerOpenError
from services.pid_state_manager import PidStateManager
from prometheus_client import Histogram, Counter
from services.pid_config_service import invalidate_cache
from actuator_registry import ActuatorRegistry

logger = logging.getLogger(__name__)

# Метрики для отслеживания производительности
ZONE_CHECKS = Counter("zone_checks_total", "Zone automation checks")
CHECK_LAT = Histogram("zone_check_seconds", "Zone check duration seconds")

# Cooldown период для контроллеров после ошибки (в секундах)
CONTROLLER_COOLDOWN_SECONDS = 60

# Backoff параметры для per-zone state
INITIAL_BACKOFF_SECONDS = 30  # Начальный backoff
MAX_BACKOFF_SECONDS = 600  # Максимальный backoff (10 минут)
BACKOFF_MULTIPLIER = 2  # Множитель для экспоненциального backoff
DEGRADED_MODE_THRESHOLD = 3  # Количество ошибок для перехода в degraded mode
SKIP_REPORT_THROTTLE_SECONDS = 120  # Троттлинг предупреждений о пропусках
COOLDOWN_SKIP_REPORT_THROTTLE_SECONDS = 120  # Троттлинг предупреждений cooldown
CONTROLLER_CIRCUIT_OPEN_ALERT_THROTTLE_SECONDS = 120  # Троттлинг CB-алертов по контроллерам
CORRECTION_FLAGS_MISSING_ALERT_THROTTLE_SECONDS = 120  # Троттлинг алертов missing_flags


class ZoneAutomationService:
    """Сервис для оркестрации автоматизации зоны."""
    
    def __init__(
        self,
        zone_repo: ZoneRepository,
        telemetry_repo: TelemetryRepository,
        node_repo: NodeRepository,
        recipe_repo: RecipeRepository,
        grow_cycle_repo: GrowCycleRepository,
        infrastructure_repo: InfrastructureRepository,
        command_bus: CommandBus,
        pid_state_manager: Optional[PidStateManager] = None
    ):
        """
        Инициализация сервиса.
        
        Args:
            zone_repo: Репозиторий зон
            telemetry_repo: Репозиторий телеметрии
            node_repo: Репозиторий узлов
            recipe_repo: Репозиторий рецептов
            grow_cycle_repo: Репозиторий циклов выращивания
            infrastructure_repo: Репозиторий инфраструктуры
            command_bus: Command Bus для публикации команд
            pid_state_manager: Менеджер состояния PID (опционально)
        """
        self.zone_repo = zone_repo
        self.telemetry_repo = telemetry_repo
        self.node_repo = node_repo
        self.recipe_repo = recipe_repo
        self.grow_cycle_repo = grow_cycle_repo
        self.infrastructure_repo = infrastructure_repo
        self.command_bus = command_bus
        self.pid_state_manager = pid_state_manager or PidStateManager()
        self.actuator_registry = ActuatorRegistry()
        
        # Инициализация контроллеров корректировки с менеджером состояния
        self.ph_controller = CorrectionController(CorrectionType.PH, self.pid_state_manager)
        self.ec_controller = CorrectionController(CorrectionType.EC, self.pid_state_manager)
        
        
        # Circuit breaker: отслеживание последних ошибок контроллеров
        # Ключ: (zone_id, controller_name), значение: datetime последней ошибки
        self._controller_failures: Dict[tuple[int, str], datetime] = {}
        
        # Per-zone state для backoff и degraded mode
        # Ключ: zone_id, значение:
        # {
        #   'error_streak': int,
        #   'next_allowed_run_at': datetime | None,
        #   'last_backoff_reported_until': datetime | None,
        #   'degraded_alert_active': bool,
        #   'last_missing_targets_report_at': datetime | None,
        #   'last_missing_correction_flags_report_at': datetime | None
        # }
        self._zone_states: Dict[int, Dict[str, Any]] = {}
        # Ключ: (zone_id, controller_name), значение: datetime последнего cooldown skip report
        self._controller_cooldown_reported_at: Dict[tuple[int, str], datetime] = {}
        # Ключ: (zone_id, controller_name), значение: datetime последнего alert о circuit-open skip
        self._controller_circuit_open_reported_at: Dict[tuple[int, str], datetime] = {}
        # Ключ: zone_id, значение: последний отправленный sensor_mode (True=activate, False=deactivate)
        self._correction_sensor_mode_state: Dict[int, bool] = {}
    
    async def save_all_pid_states(self):
        """Сохранить состояние всех PID контроллеров."""
        await self.ph_controller.save_all_states()
        await self.ec_controller.save_all_states()
    
    async def process_zone(self, zone_id: int, sim_clock: Optional[SimulationClock] = None) -> None:
        """
        Оркестрация одного цикла обработки зоны с поддержкой backoff и degraded mode.
        
        Args:
            zone_id: ID зоны для обработки
        """
        # Проверка backoff - пропускаем зону, если еще не прошло время
        if not self._should_process_zone(zone_id):
            await self._emit_backoff_skip_signal(zone_id)
            return
        
        # Определяем режим работы (normal или degraded)
        is_degraded = self._is_degraded_mode(zone_id)
        
        try:
            with CHECK_LAT.time():
                ZONE_CHECKS.inc()
                
                # Проверка удаления зоны и очистка PID инстансов (всегда выполняется)
                await self._check_zone_deletion(zone_id)
                
                # Проверка обновлений PID конфигов (всегда выполняется)
                await self._check_pid_config_updates(zone_id)
                
                # Проверка переходов фаз (стоп-условие, всегда выполняется)
                await self._check_phase_transitions(zone_id, sim_clock)
            
            # Получение данных зоны через circuit breaker
            try:
                # Получаем активный grow_cycle и targets через effective targets
                grow_cycle = await self.grow_cycle_repo.get_active_grow_cycle(zone_id)
                targets = grow_cycle.get("targets") if grow_cycle else None

                if not targets or not isinstance(targets, dict):
                    await self._emit_missing_targets_signal(zone_id, grow_cycle)
                    return

                # Получаем телеметрию и capabilities
                zone_data = await self.recipe_repo.get_zone_data_batch(zone_id)
                telemetry = zone_data.get("telemetry", {})
                telemetry_timestamps = zone_data.get("telemetry_timestamps", {})
                correction_flags = zone_data.get("correction_flags", {})
                nodes = zone_data.get("nodes", {})
                capabilities = zone_data.get("capabilities", {})
                
                # Получаем bindings для зоны
                bindings = await self.infrastructure_repo.get_zone_bindings_by_role(zone_id)
                actuators = self.actuator_registry.resolve(zone_id, bindings, nodes)
            except CircuitBreakerOpenError:
                # Circuit breaker открыт - переходим в спокойный режим
                logger.warning(
                    f"Zone {zone_id}: Database Circuit Breaker is OPEN, skipping zone processing",
                    extra={"zone_id": zone_id}
                )
                self._record_zone_error(zone_id)
                await self._emit_zone_data_unavailable_signal(zone_id)
                return
            
            normalized_correction_flags = correction_flags if isinstance(correction_flags, dict) else {}
            
            # Проверка уровня воды (safety check, всегда выполняется)
            water_level_ok, water_level = await check_water_level(zone_id)
            if water_level is not None:
                await ensure_water_level_alert(zone_id, water_level)

            sim_now = sim_clock.now() if sim_clock else utcnow()
            time_scale = sim_clock.time_scale if sim_clock else None
            
            # В degraded mode выполняем только safety checks + health + стоп-условия
            if is_degraded:
                await self._emit_degraded_mode_signal(zone_id)
                logger.warning(
                    f"Zone {zone_id}: Running in DEGRADED mode (error_streak={self._get_error_streak(zone_id)}). "
                    f"Only safety checks and health monitoring enabled.",
                    extra={'zone_id': zone_id, 'error_streak': self._get_error_streak(zone_id)}
                )
                
                # В degraded mode выполняем только:
                # - Health Monitor (всегда)
                await self._safe_process_controller(
                    'health',
                    self._update_zone_health(zone_id),
                    zone_id
                )

                # Успешное выполнение в degraded mode - сбрасываем streak
                previous_error_streak = self._reset_zone_error_streak(zone_id)
                if previous_error_streak > 0:
                    await self._emit_zone_recovered_signal(zone_id, previous_error_streak)
                return
            
            # Нормальный режим - выполняем все контроллеры
            # Обработка контроллеров в правильном порядке с изоляцией ошибок
            # 1. Light Controller
            await self._safe_process_controller(
                'light',
                self._process_light_controller(zone_id, targets, capabilities, bindings, sim_now),
                zone_id
            )
            
            # 2. Climate Controller
            await self._safe_process_controller(
                'climate',
                self._process_climate_controller(zone_id, targets, telemetry, capabilities, bindings),
                zone_id
            )
            
            # 3. Irrigation Controller
            await self._safe_process_controller(
                'irrigation',
                self._process_irrigation_controller(
                    zone_id,
                    targets,
                    telemetry,
                    capabilities,
                    water_level_ok,
                    bindings,
                    actuators,
                    sim_now,
                    time_scale,
                    sim_clock,
                ),
                zone_id
            )
            
            # 4. Recirculation Controller
            await self._safe_process_controller(
                'recirculation',
                self._process_recirculation_controller(
                    zone_id,
                    targets,
                    telemetry,
                    capabilities,
                    water_level_ok,
                    bindings,
                    actuators,
                    sim_now,
                    time_scale,
                    sim_clock,
                ),
                zone_id
            )
            
            # 5. pH/EC Correction Controllers
            await self._safe_process_controller(
                'correction',
                self._process_correction_controllers(
                    zone_id,
                    targets,
                    telemetry,
                    telemetry_timestamps,
                    normalized_correction_flags,
                    nodes,
                    capabilities,
                    water_level_ok,
                    bindings,
                    actuators,
                ),
                zone_id
            )
            
            # 6. Zone Health Monitor
            await self._safe_process_controller(
                'health',
                self._update_zone_health(zone_id),
                zone_id
            )

            # Успешное выполнение - сбрасываем error_streak
            previous_error_streak = self._reset_zone_error_streak(zone_id)
            if previous_error_streak > 0:
                await self._emit_zone_recovered_signal(zone_id, previous_error_streak)
            
        except Exception as e:
            # Ошибка при обработке зоны - увеличиваем error_streak
            self._record_zone_error(zone_id)
            
            logger.error(
                f"Zone {zone_id}: Error in process_zone: {e}",
                exc_info=True,
                extra={'zone_id': zone_id, 'error_streak': self._get_error_streak(zone_id)}
            )
            
            # Создаем событие о сбое обработки зоны
            try:
                await create_zone_event(
                    zone_id,
                    'ZONE_PROCESSING_FAILED',
                    {
                        'error': str(e),
                        'error_type': type(e).__name__,
                        'error_streak': self._get_error_streak(zone_id),
                        'next_allowed_run_at': self._get_next_allowed_run_at(zone_id).isoformat() if self._get_next_allowed_run_at(zone_id) else None
                    }
                )
            except Exception as event_error:
                logger.error(
                    f"Zone {zone_id}: Failed to create ZONE_PROCESSING_FAILED event: {event_error}",
                    exc_info=True
                )
            
            # Пробрасываем исключение дальше для обработки в main.py
            raise
    
    def _get_zone_state(self, zone_id: int) -> Dict[str, Any]:
        """
        Получить состояние зоны для backoff и degraded mode.
        
        Args:
            zone_id: ID зоны
        
        Returns:
            Dict с полями: error_streak, next_allowed_run_at
        """
        # Проверка test hook для override состояния (только в test mode)
        try:
            from api import get_zone_state_override
            state_override = get_zone_state_override(zone_id)
            if state_override:
                # Используем override из test hook
                logger.debug(
                    f"[TEST_HOOK] Using state override for zone {zone_id}: {state_override}",
                    extra={"zone_id": zone_id, "state_override": state_override}
                )
                # Обновляем внутреннее состояние
                if zone_id not in self._zone_states:
                    self._zone_states[zone_id] = {}
                self._zone_states[zone_id].update(state_override)
        except ImportError:
            # api модуль может быть недоступен
            pass
        except Exception as e:
            logger.debug(f"[TEST_HOOK] Failed to get state override: {e}")
        
        if zone_id not in self._zone_states:
            self._zone_states[zone_id] = {}

        state = self._zone_states[zone_id]
        state.setdefault('error_streak', 0)
        state.setdefault('next_allowed_run_at', None)
        state.setdefault('last_backoff_reported_until', None)
        state.setdefault('degraded_alert_active', False)
        state.setdefault('last_missing_targets_report_at', None)
        state.setdefault('last_missing_correction_flags_report_at', None)
        return state
    
    def _get_error_streak(self, zone_id: int) -> int:
        """Получить количество последовательных ошибок для зоны."""
        return self._get_zone_state(zone_id)['error_streak']
    
    def _get_next_allowed_run_at(self, zone_id: int) -> Optional[datetime]:
        """Получить время следующего разрешенного запуска для зоны."""
        return self._get_zone_state(zone_id)['next_allowed_run_at']
    
    def _should_process_zone(self, zone_id: int) -> bool:
        """
        Проверить, можно ли обрабатывать зону (проверка backoff).
        
        Args:
            zone_id: ID зоны
        
        Returns:
            True если можно обрабатывать, False если в backoff периоде
        """
        next_allowed = self._get_next_allowed_run_at(zone_id)
        if next_allowed is None:
            return True
        
        now = utcnow()
        if now < next_allowed:
            logger.debug(
                f"Zone {zone_id}: Skipping due to backoff (next allowed at {next_allowed}, now {now})",
                extra={'zone_id': zone_id, 'next_allowed_run_at': next_allowed.isoformat()}
            )
            return False
        
        return True
    
    def _is_degraded_mode(self, zone_id: int) -> bool:
        """
        Проверить, находится ли зона в degraded mode.
        
        Args:
            zone_id: ID зоны
        
        Returns:
            True если в degraded mode (error_streak >= DEGRADED_MODE_THRESHOLD)
        """
        return self._get_error_streak(zone_id) >= DEGRADED_MODE_THRESHOLD
    
    def _calculate_backoff_seconds(self, error_streak: int) -> int:
        """
        Вычислить время backoff в секундах на основе error_streak.
        
        Использует экспоненциальный backoff: INITIAL_BACKOFF_SECONDS * (BACKOFF_MULTIPLIER ^ error_streak)
        
        Args:
            error_streak: Количество последовательных ошибок
        
        Returns:
            Время backoff в секундах (ограничено MAX_BACKOFF_SECONDS)
        """
        if error_streak <= 0:
            return 0
        
        backoff = INITIAL_BACKOFF_SECONDS * (BACKOFF_MULTIPLIER ** (error_streak - 1))
        return min(int(backoff), MAX_BACKOFF_SECONDS)
    
    def _record_zone_error(self, zone_id: int) -> None:
        """
        Записать ошибку для зоны и вычислить next_allowed_run_at с экспоненциальным backoff.
        
        Args:
            zone_id: ID зоны
        """
        state = self._get_zone_state(zone_id)
        state['error_streak'] += 1
        
        # Вычисляем backoff
        backoff_seconds = self._calculate_backoff_seconds(state['error_streak'])
        state['next_allowed_run_at'] = utcnow() + timedelta(seconds=backoff_seconds)
        
        logger.warning(
            f"Zone {zone_id}: Error recorded. error_streak={state['error_streak']}, "
            f"backoff={backoff_seconds}s, next_allowed_run_at={state['next_allowed_run_at']}",
            extra={
                'zone_id': zone_id,
                'error_streak': state['error_streak'],
                'backoff_seconds': backoff_seconds,
                'next_allowed_run_at': state['next_allowed_run_at'].isoformat()
            }
        )
    
    def _reset_zone_error_streak(self, zone_id: int) -> int:
        """
        Сбросить error_streak для зоны после успешного выполнения.
        
        Args:
            zone_id: ID зоны
        """
        state = self._get_zone_state(zone_id)
        previous_error_streak = int(state['error_streak'])
        if state['error_streak'] > 0:
            logger.info(
                f"Zone {zone_id}: Resetting error_streak (was {state['error_streak']}) after successful cycle",
                extra={'zone_id': zone_id, 'previous_error_streak': state['error_streak']}
            )
        
        state['error_streak'] = 0
        state['next_allowed_run_at'] = None
        state['last_backoff_reported_until'] = None
        state['degraded_alert_active'] = False
        return previous_error_streak

    async def _create_zone_event_safe(
        self,
        zone_id: int,
        event_type: str,
        details: Dict[str, Any],
        signal_name: str,
    ) -> bool:
        """
        Безопасно создать zone_event.
        При сбое пишет error-сигнал в infra alerts, чтобы не было тихих потерь событий.
        """
        try:
            await create_zone_event(zone_id, event_type, details)
            return True
        except Exception as event_error:
            logger.warning(
                "Zone %s: Failed to create %s event: %s",
                zone_id,
                event_type,
                event_error,
                exc_info=True,
            )
            await send_infra_exception_alert(
                error=event_error,
                code="infra_zone_event_write_failed",
                alert_type="Zone Event Write Failed",
                severity="error",
                zone_id=zone_id,
                service="automation-engine",
                component="zone_events",
                details={
                    "event_type": event_type,
                    "signal_name": signal_name,
                },
            )
            return False

    async def _emit_backoff_skip_signal(self, zone_id: int) -> None:
        """Лог/ивент/алерт при пропуске зоны из-за backoff (с защитой от спама)."""
        state = self._get_zone_state(zone_id)
        next_allowed = state.get('next_allowed_run_at')
        if not next_allowed:
            return

        now = utcnow()
        remaining_seconds = max(0, int((next_allowed - now).total_seconds()))
        already_reported_until = state.get('last_backoff_reported_until')
        if already_reported_until == next_allowed:
            logger.debug(
                "Zone %s: Backoff skip (already reported), remaining=%ss",
                zone_id,
                remaining_seconds,
                extra={'zone_id': zone_id, 'next_allowed_run_at': next_allowed.isoformat()},
            )
            return

        logger.warning(
            "Zone %s: Skipped due to backoff, remaining=%ss, next_allowed_run_at=%s",
            zone_id,
            remaining_seconds,
            next_allowed.isoformat(),
            extra={
                'zone_id': zone_id,
                'error_streak': self._get_error_streak(zone_id),
                'next_allowed_run_at': next_allowed.isoformat(),
                'remaining_seconds': remaining_seconds,
            },
        )

        event_created = await self._create_zone_event_safe(
            zone_id=zone_id,
            event_type='ZONE_SKIPPED_BACKOFF',
            details={
                'error_streak': self._get_error_streak(zone_id),
                'next_allowed_run_at': next_allowed.isoformat(),
                'remaining_seconds': remaining_seconds,
            },
            signal_name="backoff_skip",
        )
        alert_sent = await send_infra_alert(
            code="infra_zone_backoff_skip",
            alert_type="Zone Backoff Skip",
            message=f"Zone {zone_id} skipped due to backoff",
            severity="warning",
            zone_id=zone_id,
            service="automation-engine",
            component="zone_processing",
            error_type="BackoffSkip",
            details={
                "error_streak": self._get_error_streak(zone_id),
                "next_allowed_run_at": next_allowed.isoformat(),
                "remaining_seconds": remaining_seconds,
            },
        )
        if event_created or alert_sent:
            state['last_backoff_reported_until'] = next_allowed
        else:
            logger.warning(
                "Zone %s: Backoff skip signal not persisted (event+alert failed), will retry",
                zone_id,
                extra={'zone_id': zone_id, 'next_allowed_run_at': next_allowed.isoformat()},
            )

    async def _emit_missing_targets_signal(self, zone_id: int, grow_cycle: Optional[Dict[str, Any]]) -> None:
        """Лог/ивент/алерт при отсутствии targets (чтобы не было тихого return)."""
        state = self._get_zone_state(zone_id)
        now = utcnow()
        last_reported = state.get('last_missing_targets_report_at')
        if isinstance(last_reported, datetime) and (now - last_reported).total_seconds() < SKIP_REPORT_THROTTLE_SECONDS:
            logger.debug(
                "Zone %s: Missing targets (throttled report)",
                zone_id,
                extra={'zone_id': zone_id},
            )
            return

        logger.warning(
            "Zone %s: Skipping processing because targets are missing or invalid",
            zone_id,
            extra={'zone_id': zone_id, 'grow_cycle_present': bool(grow_cycle)},
        )

        event_created = await self._create_zone_event_safe(
            zone_id=zone_id,
            event_type='ZONE_SKIPPED_NO_TARGETS',
            details={
                'grow_cycle_present': bool(grow_cycle),
                'reason': 'targets_missing_or_invalid',
            },
            signal_name="missing_targets",
        )
        alert_sent = await send_infra_alert(
            code="infra_zone_targets_missing",
            alert_type="Zone Targets Missing",
            message=f"Zone {zone_id} skipped: targets are missing or invalid",
            severity="warning",
            zone_id=zone_id,
            service="automation-engine",
            component="zone_processing",
            error_type="MissingTargets",
            details={"grow_cycle_present": bool(grow_cycle)},
        )
        if event_created or alert_sent:
            state['last_missing_targets_report_at'] = now
        else:
            logger.warning(
                "Zone %s: Missing-targets signal not persisted (event+alert failed), will retry",
                zone_id,
                extra={'zone_id': zone_id},
            )

    async def _emit_correction_missing_flags_signal(
        self,
        zone_id: int,
        gating_state: Dict[str, Any],
        nodes: Dict[str, Dict[str, Any]],
    ) -> None:
        """Инфра-алерт о пропуске коррекций из-за отсутствия sensor-mode flags."""
        state = self._get_zone_state(zone_id)
        now = utcnow()
        last_reported = state.get('last_missing_correction_flags_report_at')
        if isinstance(last_reported, datetime) and (
            now - last_reported
        ).total_seconds() < CORRECTION_FLAGS_MISSING_ALERT_THROTTLE_SECONDS:
            return

        missing_flags = list(gating_state.get("missing_flags") or [])
        correction_flags = gating_state.get("flags") if isinstance(gating_state.get("flags"), dict) else {}
        sensor_nodes = [node.get("node_uid") for node in self._resolve_correction_sensor_nodes(nodes)]

        logger.warning(
            "Zone %s: correction skipped, missing flags=%s, sensor_nodes=%s",
            zone_id,
            missing_flags,
            sensor_nodes,
            extra={
                "zone_id": zone_id,
                "missing_flags": missing_flags,
                "sensor_nodes": sensor_nodes,
                "correction_flags": correction_flags,
            },
        )

        alert_sent = await send_infra_alert(
            code="infra_correction_flags_missing",
            alert_type="Correction Flags Missing",
            message=f"Zone {zone_id} skipped correction due to missing sensor-mode flags",
            severity="warning",
            zone_id=zone_id,
            service="automation-engine",
            component="correction_gating",
            error_type="missing_flags",
            details={
                "missing_flags": missing_flags,
                "correction_flags": correction_flags,
                "sensor_nodes": sensor_nodes,
                "throttle_seconds": CORRECTION_FLAGS_MISSING_ALERT_THROTTLE_SECONDS,
            },
        )
        if alert_sent:
            state['last_missing_correction_flags_report_at'] = now

    async def _emit_zone_data_unavailable_signal(self, zone_id: int) -> None:
        """Лог/ивент/алерт при недоступности данных зоны (DB circuit breaker open)."""
        state = self._get_zone_state(zone_id)
        next_allowed = state.get('next_allowed_run_at')
        error_streak = state.get('error_streak', 0)
        logger.warning(
            "Zone %s: Zone data unavailable, scheduling retry with backoff",
            zone_id,
            extra={
                'zone_id': zone_id,
                'error_streak': error_streak,
                'next_allowed_run_at': next_allowed.isoformat() if next_allowed else None,
            },
        )

        await self._create_zone_event_safe(
            zone_id=zone_id,
            event_type='ZONE_DATA_UNAVAILABLE',
            details={
                'reason': 'db_circuit_breaker_open',
                'error_streak': error_streak,
                'next_allowed_run_at': next_allowed.isoformat() if next_allowed else None,
            },
            signal_name="zone_data_unavailable",
        )

        await send_infra_alert(
            code="infra_zone_data_unavailable",
            alert_type="Zone Data Unavailable",
            message=f"Zone {zone_id} data unavailable due to opened database circuit breaker",
            severity="error",
            zone_id=zone_id,
            service="automation-engine",
            component="zone_processing",
            error_type="CircuitBreakerOpenError",
            details={
                "error_streak": error_streak,
                "next_allowed_run_at": next_allowed.isoformat() if next_allowed else None,
            },
        )

    async def _emit_degraded_mode_signal(self, zone_id: int) -> None:
        """Лог/ивент/алерт при входе в degraded mode (один раз на инцидент)."""
        state = self._get_zone_state(zone_id)
        if state.get('degraded_alert_active', False):
            return

        error_streak = int(state.get('error_streak', 0))
        logger.warning(
            "Zone %s: Entered DEGRADED mode (error_streak=%s)",
            zone_id,
            error_streak,
            extra={'zone_id': zone_id, 'error_streak': error_streak},
        )

        event_created = await self._create_zone_event_safe(
            zone_id=zone_id,
            event_type='ZONE_DEGRADED_MODE',
            details={
                'error_streak': error_streak,
                'threshold': DEGRADED_MODE_THRESHOLD,
            },
            signal_name="degraded_mode",
        )

        alert_sent = await send_infra_alert(
            code="infra_zone_degraded_mode",
            alert_type="Zone Degraded Mode",
            message=f"Zone {zone_id} switched to degraded mode",
            severity="error",
            zone_id=zone_id,
            service="automation-engine",
            component="zone_processing",
            error_type="DegradedMode",
            details={
                "error_streak": error_streak,
                "threshold": DEGRADED_MODE_THRESHOLD,
            },
        )
        if event_created or alert_sent:
            state['degraded_alert_active'] = True
        else:
            logger.warning(
                "Zone %s: Degraded-mode signal not persisted (event+alert failed), will retry",
                zone_id,
                extra={'zone_id': zone_id, 'error_streak': error_streak},
            )

    async def _emit_zone_recovered_signal(self, zone_id: int, previous_error_streak: int) -> None:
        """Явный recovery-сигнал в логи и zone_events после серии ошибок."""
        logger.info(
            "Zone %s: Recovered after %s consecutive errors",
            zone_id,
            previous_error_streak,
            extra={'zone_id': zone_id, 'previous_error_streak': previous_error_streak},
        )
        await self._create_zone_event_safe(
            zone_id=zone_id,
            event_type='ZONE_RECOVERED',
            details={
                'previous_error_streak': previous_error_streak,
            },
            signal_name="zone_recovered",
        )
        for resolved_code in (
            "infra_zone_degraded_mode",
            "infra_zone_data_unavailable",
            "infra_zone_backoff_skip",
            "infra_zone_targets_missing",
        ):
            await send_infra_resolved_alert(
                code=resolved_code,
                alert_type="Zone Recovered",
                message=f"Zone {zone_id} recovered after {previous_error_streak} consecutive errors",
                zone_id=zone_id,
                service="automation-engine",
                component="zone_processing",
                details={"previous_error_streak": previous_error_streak},
            )

    async def _emit_controller_circuit_open_signal(
        self,
        zone_id: int,
        controller_name: str,
        *,
        channel: Optional[str] = None,
        cmd: Optional[str] = None,
    ) -> None:
        """Алерт о пропуске команды из-за открытого API Circuit Breaker (с троттлингом)."""
        key = (zone_id, controller_name)
        now = utcnow()
        last_reported = self._controller_circuit_open_reported_at.get(key)
        if last_reported and (now - last_reported).total_seconds() < CONTROLLER_CIRCUIT_OPEN_ALERT_THROTTLE_SECONDS:
            return

        alert_sent = await send_infra_alert(
            code="infra_controller_command_skipped_circuit_open",
            alert_type="Controller Command Skipped (Circuit Open)",
            message=f"Zone {zone_id} controller '{controller_name}' skipped command due to open API circuit breaker",
            severity="error",
            zone_id=zone_id,
            service="automation-engine",
            component=f"controller:{controller_name}",
            channel=channel,
            cmd=cmd,
            error_type="CircuitBreakerOpenError",
            details={
                "controller": controller_name,
                "throttle_seconds": CONTROLLER_CIRCUIT_OPEN_ALERT_THROTTLE_SECONDS,
            },
        )
        if alert_sent:
            self._controller_circuit_open_reported_at[key] = now
    
    def _is_controller_in_cooldown(self, zone_id: int, controller_name: str) -> bool:
        """
        Проверить, находится ли контроллер в cooldown периоде после ошибки.
        
        Args:
            zone_id: ID зоны
            controller_name: Имя контроллера ('light', 'climate', 'irrigation', 'recirculation', 'correction', 'health')
        
        Returns:
            True если контроллер в cooldown, False если можно выполнять
        """
        key = (zone_id, controller_name)
        if key not in self._controller_failures:
            return False
        
        last_failure = self._controller_failures[key]
        cooldown_end = last_failure + timedelta(seconds=CONTROLLER_COOLDOWN_SECONDS)
        return utcnow() < cooldown_end
    
    def _record_controller_failure(self, zone_id: int, controller_name: str) -> None:
        """
        Записать время последней ошибки контроллера.
        
        Args:
            zone_id: ID зоны
            controller_name: Имя контроллера
        """
        key = (zone_id, controller_name)
        self._controller_failures[key] = utcnow()
        self._controller_cooldown_reported_at.pop(key, None)
    
    async def _safe_process_controller(
        self,
        controller_name: str,
        controller_coro,
        zone_id: int
    ) -> None:
        """
        Безопасная обработка контроллера с изоляцией ошибок и поддержкой test hooks.
        
        Args:
            controller_name: Имя контроллера (climate, ph, ec, irrigation, etc.)
            controller_coro: Корутина для выполнения контроллера
            zone_id: ID зоны
        """
        # Проверка test hook для детерминированных ошибок (только в test mode)
        try:
            from api import get_test_hook_for_zone
            test_hook = get_test_hook_for_zone(zone_id, controller_name)
            if test_hook and test_hook.get("active"):
                error_type = test_hook.get("error_type", "ControllerError")
                logger.warning(
                    f"[TEST_HOOK] Injecting error for zone {zone_id}, controller {controller_name}: {error_type}",
                    extra={"zone_id": zone_id, "controller": controller_name, "error_type": error_type}
                )
                # Создаем событие о принудительной ошибке
                await create_zone_event(
                    zone_id,
                    'CONTROLLER_FAILED',
                    {
                        'controller': controller_name,
                        'error_type': error_type,
                        'test_hook': True
                    }
                )
                # Выбрасываем исключение в зависимости от типа
                if error_type == "ControllerError":
                    raise RuntimeError(f"[TEST_HOOK] Forced controller error: {controller_name}")
                elif error_type == "TimeoutError":
                    raise TimeoutError(f"[TEST_HOOK] Forced timeout: {controller_name}")
                else:
                    raise Exception(f"[TEST_HOOK] Forced error ({error_type}): {controller_name}")
        except ImportError:
            # api модуль может быть недоступен в некоторых контекстах
            pass
        except Exception as e:
            # Если test hook сам вызвал ошибку, пробрасываем её дальше
            raise
        """
        Безопасное выполнение контроллера с изоляцией ошибок.
        
        Args:
            controller_name: Имя контроллера для логирования
            controller_coro: Корутина контроллера (awaitable)
            zone_id: ID зоны
        """
        # Проверяем cooldown
        if self._is_controller_in_cooldown(zone_id, controller_name):
            # Корутину создают до входа в _safe_process_controller.
            # Если контроллер в cooldown, нужно явно закрыть её,
            # иначе остаются "висящие" coroutine-объекты.
            if inspect.iscoroutine(controller_coro):
                controller_coro.close()
            await self._emit_controller_cooldown_skip_signal(zone_id, controller_name)
            return
        
        try:
            await controller_coro
            # Если выполнение успешно, очищаем запись об ошибке (если была)
            key = (zone_id, controller_name)
            if key in self._controller_failures:
                del self._controller_failures[key]
            self._controller_cooldown_reported_at.pop(key, None)
        except Exception as e:
            # Записываем время ошибки для cooldown
            self._record_controller_failure(zone_id, controller_name)
            
            # Логируем ошибку
            logger.error(
                f"Zone {zone_id}: Controller '{controller_name}' failed: {e}",
                exc_info=True,
                extra={'zone_id': zone_id, 'controller': controller_name, 'error': str(e)}
            )
            
            # Создаем событие о сбое контроллера
            try:
                await create_zone_event(
                    zone_id,
                    'CONTROLLER_FAILED',
                    {
                        'controller': controller_name,
                        'error': str(e),
                        'error_type': type(e).__name__,
                        'cooldown_seconds': CONTROLLER_COOLDOWN_SECONDS
                    }
                )
            except Exception as event_error:
                logger.error(
                    f"Zone {zone_id}: Failed to create CONTROLLER_FAILED event: {event_error}",
                    exc_info=True
                )

            await send_infra_exception_alert(
                error=e,
                code="infra_controller_failed",
                alert_type="Controller Failed",
                severity="error",
                zone_id=zone_id,
                service="automation-engine",
                component=f"controller:{controller_name}",
                details={
                    "controller": controller_name,
                    "cooldown_seconds": CONTROLLER_COOLDOWN_SECONDS,
                },
            )

    async def _emit_controller_cooldown_skip_signal(self, zone_id: int, controller_name: str) -> None:
        """Лог/ивент/алерт при skip контроллера в cooldown с троттлингом."""
        key = (zone_id, controller_name)
        now = utcnow()
        last_reported = self._controller_cooldown_reported_at.get(key)
        if last_reported and (now - last_reported).total_seconds() < COOLDOWN_SKIP_REPORT_THROTTLE_SECONDS:
            logger.debug(
                "Zone %s: Controller '%s' cooldown skip (throttled report)",
                zone_id,
                controller_name,
                extra={'zone_id': zone_id, 'controller': controller_name},
            )
            return

        last_failure = self._controller_failures.get(key)
        cooldown_end = (
            last_failure + timedelta(seconds=CONTROLLER_COOLDOWN_SECONDS)
            if last_failure
            else None
        )
        remaining_seconds = (
            max(0, int((cooldown_end - now).total_seconds()))
            if cooldown_end
            else CONTROLLER_COOLDOWN_SECONDS
        )

        logger.warning(
            "Zone %s: Controller '%s' skipped due to cooldown, remaining=%ss",
            zone_id,
            controller_name,
            remaining_seconds,
            extra={
                'zone_id': zone_id,
                'controller': controller_name,
                'remaining_seconds': remaining_seconds,
            },
        )

        event_created = await self._create_zone_event_safe(
            zone_id=zone_id,
            event_type='CONTROLLER_COOLDOWN_SKIP',
            details={
                'controller': controller_name,
                'cooldown_seconds': CONTROLLER_COOLDOWN_SECONDS,
                'remaining_seconds': remaining_seconds,
            },
            signal_name="controller_cooldown_skip",
        )

        alert_sent = await send_infra_alert(
            code="infra_controller_cooldown_skip",
            alert_type="Controller Cooldown Skip",
            message=f"Zone {zone_id} controller '{controller_name}' skipped due to cooldown",
            severity="warning",
            zone_id=zone_id,
            service="automation-engine",
            component=f"controller:{controller_name}",
            error_type="ControllerCooldown",
            details={
                "controller": controller_name,
                "cooldown_seconds": CONTROLLER_COOLDOWN_SECONDS,
                "remaining_seconds": remaining_seconds,
            },
        )
        if event_created or alert_sent:
            self._controller_cooldown_reported_at[key] = now
        else:
            logger.warning(
                "Zone %s: Cooldown skip signal for controller '%s' not persisted, will retry",
                zone_id,
                controller_name,
                extra={'zone_id': zone_id, 'controller': controller_name},
            )
    
    async def _check_phase_transitions(
        self,
        zone_id: int,
        sim_clock: Optional[SimulationClock] = None,
    ) -> None:
        """
        Проверка и переход между фазами рецепта по simulated-time.
        Для production-циклов без sim_clock переходы не выполняются.
        """
        if not sim_clock:
            return
        if sim_clock.mode == "live":
            return

        phase_info = await self.grow_cycle_repo.get_current_phase_timing(zone_id)
        if not phase_info:
            return

        duration_hours = phase_info.get("duration_hours")
        duration_days = phase_info.get("duration_days")
        if duration_hours is None and duration_days is None:
            return

        duration_hours_value = float(duration_hours) if duration_hours is not None else float(duration_days) * 24.0
        if duration_hours_value <= 0:
            return

        phase_started_at = phase_info.get("phase_started_at") or phase_info.get("recipe_started_at")
        if not phase_started_at:
            return

        sim_now = sim_clock.now()
        phase_start_sim = sim_clock.to_sim_time(phase_started_at)
        if sim_now < phase_start_sim:
            return

        elapsed_hours = (sim_now - phase_start_sim).total_seconds() / 3600.0
        if elapsed_hours < duration_hours_value:
            return

        grow_cycle_id = phase_info.get("grow_cycle_id")
        if not grow_cycle_id:
            return

        phase_index = phase_info.get("phase_index")
        max_phase_index = phase_info.get("max_phase_index")

        try:
            if max_phase_index is not None and phase_index is not None and phase_index >= max_phase_index:
                success = await self.grow_cycle_repo.harvest_cycle(int(grow_cycle_id))
                if success:
                    await record_simulation_event(
                        zone_id=zone_id,
                        service="automation-engine",
                        stage="phase_transition",
                        status="harvested",
                        message="Simulation cycle harvested",
                        payload={
                            "grow_cycle_id": grow_cycle_id,
                            "phase_index": phase_index,
                            "elapsed_hours": elapsed_hours,
                        },
                    )
                return

            success = await self.grow_cycle_repo.advance_phase(int(grow_cycle_id))
            if success:
                await record_simulation_event(
                    zone_id=zone_id,
                    service="automation-engine",
                    stage="phase_transition",
                    status="advanced",
                    message="Simulation phase advanced",
                    payload={
                        "grow_cycle_id": grow_cycle_id,
                        "phase_index": phase_index,
                        "elapsed_hours": elapsed_hours,
                    },
                )
        except CircuitBreakerOpenError:
            logger.warning(
                "Zone %s: Circuit Breaker open during phase transition",
                zone_id,
                extra={"zone_id": zone_id},
            )
            await self._emit_controller_circuit_open_signal(zone_id, "phase_transition")
    
    async def _process_light_controller(
        self,
        zone_id: int,
        targets: Dict[str, Any],
        capabilities: Dict[str, bool],
        bindings: Dict[str, Dict[str, Any]],
        current_time: datetime,
    ) -> None:
        """Обработка контроллера освещения."""
        if not capabilities.get("light_control", False):
            return
        
        light_cmd = await check_and_control_lighting(zone_id, targets, bindings, current_time)
        if light_cmd:
            if light_cmd.get('event_type'):
                await create_zone_event(zone_id, light_cmd['event_type'], light_cmd.get('event_details', {}))
            try:
                await self.command_bus.publish_controller_command(zone_id, light_cmd)
            except CircuitBreakerOpenError:
                logger.warning(
                    f"Zone {zone_id}: API Circuit Breaker is OPEN, skipping light command",
                    extra={"zone_id": zone_id}
                )
                await self._emit_controller_circuit_open_signal(
                    zone_id,
                    "light",
                    channel=light_cmd.get("channel"),
                    cmd=light_cmd.get("cmd"),
                )
    
    async def _process_climate_controller(
        self,
        zone_id: int,
        targets: Dict[str, Any],
        telemetry: Dict[str, Optional[float]],
        capabilities: Dict[str, bool],
        bindings: Dict[str, Dict[str, Any]]
    ) -> None:
        """Обработка контроллера климата."""
        if not capabilities.get("climate_control", False):
            return
        
        climate_commands = await check_and_control_climate(zone_id, targets, telemetry, bindings)
        for cmd in climate_commands:
            if cmd.get('event_type'):
                await create_zone_event(zone_id, cmd['event_type'], cmd.get('event_details', {}))
            try:
                await self.command_bus.publish_controller_command(zone_id, cmd)
            except CircuitBreakerOpenError:
                logger.warning(
                    f"Zone {zone_id}: API Circuit Breaker is OPEN, skipping climate command",
                    extra={"zone_id": zone_id}
                )
                await self._emit_controller_circuit_open_signal(
                    zone_id,
                    "climate",
                    channel=cmd.get("channel"),
                    cmd=cmd.get("cmd"),
                )
                break  # Прерываем цикл при открытом circuit breaker
    
    async def _process_irrigation_controller(
        self,
        zone_id: int,
        targets: Dict[str, Any],
        telemetry: Dict[str, Optional[float]],
        capabilities: Dict[str, bool],
        water_level_ok: bool,
        bindings: Dict[str, Dict[str, Any]],
        actuators: Dict[str, Dict[str, Any]],
        current_time: datetime,
        time_scale: Optional[float],
        sim_clock: Optional[SimulationClock],
    ) -> None:
        """Обработка контроллера полива."""
        if not capabilities.get("irrigation_control", False):
            return
        
        irrigation_cmd = await check_and_control_irrigation(
            zone_id,
            targets,
            telemetry,
            bindings,
            actuators,
            current_time=current_time,
            time_scale=time_scale,
            sim_clock=sim_clock,
        )
        
        # Проверка безопасности перед запуском насоса
        if irrigation_cmd:
            pump_channel = irrigation_cmd.get('channel', 'default')
            can_run, error_msg = await can_run_pump(zone_id, pump_channel)
            if not can_run:
                logger.warning(f"Zone {zone_id}: Cannot run irrigation pump {pump_channel}: {error_msg}")
                await send_infra_alert(
                    code="infra_irrigation_pump_blocked",
                    alert_type="Irrigation Pump Blocked",
                    message=f"Zone {zone_id}: irrigation pump blocked by safety rules",
                    severity="error",
                    zone_id=zone_id,
                    service="automation-engine",
                    component="controller:irrigation",
                    channel=pump_channel,
                    cmd="run_pump",
                    error_type="PumpSafetyBlocked",
                    details={"reason": error_msg},
                )
                irrigation_cmd = None
        
        if irrigation_cmd:
            if irrigation_cmd.get('event_type'):
                await create_zone_event(zone_id, irrigation_cmd['event_type'], irrigation_cmd.get('event_details', {}))
            try:
                await self.command_bus.publish_controller_command(zone_id, irrigation_cmd)
            except CircuitBreakerOpenError:
                logger.warning(
                    f"Zone {zone_id}: API Circuit Breaker is OPEN, skipping irrigation command",
                    extra={"zone_id": zone_id}
                )
                await self._emit_controller_circuit_open_signal(
                    zone_id,
                    "irrigation",
                    channel=irrigation_cmd.get("channel"),
                    cmd=irrigation_cmd.get("cmd"),
                )
    
    async def _process_recirculation_controller(
        self,
        zone_id: int,
        targets: Dict[str, Any],
        telemetry: Dict[str, Optional[float]],
        capabilities: Dict[str, bool],
        water_level_ok: bool,
        bindings: Dict[str, Dict[str, Any]],
        actuators: Dict[str, Dict[str, Any]],
        current_time: datetime,
        time_scale: Optional[float],
        sim_clock: Optional[SimulationClock],
    ) -> None:
        """Обработка контроллера рециркуляции."""
        if not capabilities.get("recirculation", False):
            return
        
        recirculation_cmd = await check_and_control_recirculation(
            zone_id,
            targets,
            telemetry,
            bindings,
            actuators,
            current_time=current_time,
            time_scale=time_scale,
            sim_clock=sim_clock,
        )
        if recirculation_cmd:
            if recirculation_cmd.get('event_type'):
                await create_zone_event(zone_id, recirculation_cmd['event_type'], recirculation_cmd.get('event_details', {}))
            try:
                await self.command_bus.publish_controller_command(zone_id, recirculation_cmd)
            except CircuitBreakerOpenError:
                logger.warning(
                    f"Zone {zone_id}: API Circuit Breaker is OPEN, skipping recirculation command",
                    extra={"zone_id": zone_id}
                )
                await self._emit_controller_circuit_open_signal(
                    zone_id,
                    "recirculation",
                    channel=recirculation_cmd.get("channel"),
                    cmd=recirculation_cmd.get("cmd"),
                )
    
    async def _process_correction_controllers(
        self,
        zone_id: int,
        targets: Dict[str, Any],
        telemetry: Dict[str, Optional[float]],
        telemetry_timestamps: Dict[str, Any],
        correction_flags: Dict[str, Any],
        nodes: Dict[str, Dict[str, Any]],
        capabilities: Dict[str, bool],
        water_level_ok: bool,
        bindings: Dict[str, Dict[str, Any]],
        actuators: Dict[str, Dict[str, Any]]
    ) -> None:
        """Обработка контроллеров корректировки pH/EC."""
        gating_state = self._build_correction_gating_state(
            telemetry=telemetry,
            telemetry_timestamps=telemetry_timestamps,
            correction_flags=correction_flags,
        )
        if gating_state["missing_flags"]:
            await create_zone_event(
                zone_id,
                "CORRECTION_SKIPPED_MISSING_FLAGS",
                {
                    "reason_code": "missing_flags",
                    "missing_flags": gating_state["missing_flags"],
                    "correction_flags": gating_state["flags"],
                },
            )
            await self._emit_correction_missing_flags_signal(zone_id, gating_state, nodes)
            await self._set_sensor_mode(
                zone_id=zone_id,
                nodes=nodes,
                activate=True,
                reason="missing_flags",
            )
            return

        if not gating_state["can_run"]:
            reason_code = str(gating_state["reason_code"] or "correction_flags_blocked")
            await create_zone_event(
                zone_id,
                "CORRECTION_SKIPPED_FLAGS_GATING",
                {
                    "reason_code": reason_code,
                    "correction_flags": gating_state["flags"],
                },
            )
            if reason_code == "flow_inactive":
                await self._set_sensor_mode(
                    zone_id=zone_id,
                    nodes=nodes,
                    activate=False,
                    reason=reason_code,
                )
            return

        await self._set_sensor_mode(
            zone_id=zone_id,
            nodes=nodes,
            activate=True,
            reason="correction_gating_passed",
        )
        
        # pH Correction
        if capabilities.get("ph_control", False):
            ph_cmd = await self.ph_controller.check_and_correct(
                zone_id, targets, telemetry, telemetry_timestamps, nodes, water_level_ok, actuators
            )
            if ph_cmd:
                # Получаем PID для контекста
                pid = self.ph_controller._pid_by_zone.get(zone_id)
                try:
                    await self.ph_controller.apply_correction(ph_cmd, self.command_bus, pid)
                except CircuitBreakerOpenError:
                    logger.warning(
                        f"Zone {zone_id}: API Circuit Breaker is OPEN, skipping PH correction command",
                        extra={"zone_id": zone_id}
                    )
                    await self._emit_controller_circuit_open_signal(
                        zone_id,
                        "ph_correction",
                        channel=ph_cmd.get("channel"),
                        cmd=ph_cmd.get("cmd"),
                    )
        
        # EC Correction
        if capabilities.get("ec_control", False):
            ec_cmd = await self.ec_controller.check_and_correct(
                zone_id, targets, telemetry, telemetry_timestamps, nodes, water_level_ok, actuators
            )
            if ec_cmd:
                # Получаем PID для контекста
                pid = self.ec_controller._pid_by_zone.get(zone_id)
                try:
                    await self.ec_controller.apply_correction(ec_cmd, self.command_bus, pid)
                except CircuitBreakerOpenError:
                    logger.warning(
                        f"Zone {zone_id}: API Circuit Breaker is OPEN, skipping EC correction command",
                        extra={"zone_id": zone_id}
                    )
                    await self._emit_controller_circuit_open_signal(
                        zone_id,
                        "ec_correction",
                        channel=ec_cmd.get("channel"),
                        cmd=ec_cmd.get("cmd"),
                    )

    @staticmethod
    def _normalize_optional_bool(raw: Any) -> Optional[bool]:
        if isinstance(raw, bool):
            return raw
        if isinstance(raw, (int, float)):
            if raw == 1:
                return True
            if raw == 0:
                return False
            return None
        if isinstance(raw, str):
            normalized = raw.strip().lower()
            if normalized in {"1", "true", "yes", "on"}:
                return True
            if normalized in {"0", "false", "no", "off"}:
                return False
        return None

    def _build_correction_gating_state(
        self,
        *,
        telemetry: Dict[str, Optional[float]],
        telemetry_timestamps: Dict[str, Any],
        correction_flags: Dict[str, Any],
    ) -> Dict[str, Any]:
        flags = correction_flags if isinstance(correction_flags, dict) else {}
        flow_active_raw = flags.get("flow_active", telemetry.get("FLOW_ACTIVE"))
        stable_raw = flags.get("stable", telemetry.get("STABLE"))
        corrections_allowed_raw = flags.get("corrections_allowed", telemetry.get("CORRECTIONS_ALLOWED"))
        flow_active = self._normalize_optional_bool(flow_active_raw)
        stable = self._normalize_optional_bool(stable_raw)
        corrections_allowed = self._normalize_optional_bool(corrections_allowed_raw)
        normalized_flags = {
            "flow_active": flow_active,
            "stable": stable,
            "corrections_allowed": corrections_allowed,
            "flow_active_ts": flags.get("flow_active_ts", telemetry_timestamps.get("FLOW_ACTIVE")),
            "stable_ts": flags.get("stable_ts", telemetry_timestamps.get("STABLE")),
            "corrections_allowed_ts": flags.get("corrections_allowed_ts", telemetry_timestamps.get("CORRECTIONS_ALLOWED")),
        }
        missing_flags = [name for name in ("flow_active", "stable", "corrections_allowed") if normalized_flags[name] is None]
        if missing_flags:
            return {
                "can_run": False,
                "reason_code": "missing_flags",
                "missing_flags": missing_flags,
                "flags": normalized_flags,
            }
        if not normalized_flags["flow_active"]:
            return {"can_run": False, "reason_code": "flow_inactive", "missing_flags": [], "flags": normalized_flags}
        if not normalized_flags["stable"]:
            return {"can_run": False, "reason_code": "sensor_unstable", "missing_flags": [], "flags": normalized_flags}
        if not normalized_flags["corrections_allowed"]:
            return {"can_run": False, "reason_code": "corrections_not_allowed", "missing_flags": [], "flags": normalized_flags}
        return {"can_run": True, "reason_code": "gating_passed", "missing_flags": [], "flags": normalized_flags}

    @staticmethod
    def _resolve_correction_sensor_nodes(nodes: Dict[str, Dict[str, Any]]) -> List[Dict[str, Any]]:
        result: List[Dict[str, Any]] = []
        seen = set()
        for node in (nodes or {}).values():
            if not isinstance(node, dict):
                continue
            node_type = str(node.get("type") or "").strip().lower()
            if node_type not in {"ph", "ec"}:
                continue
            node_uid = str(node.get("node_uid") or "").strip()
            if not node_uid:
                continue
            if node_uid in seen:
                continue
            seen.add(node_uid)
            result.append({"node_uid": node_uid, "type": node_type})
        return result

    async def _set_sensor_mode(
        self,
        *,
        zone_id: int,
        nodes: Dict[str, Dict[str, Any]],
        activate: bool,
        reason: str,
    ) -> None:
        previous_state = self._correction_sensor_mode_state.get(zone_id)
        if previous_state is not None and previous_state == activate:
            return
        sensor_nodes = self._resolve_correction_sensor_nodes(nodes)
        if not sensor_nodes:
            return

        cmd = "activate_sensor_mode" if activate else "deactivate_sensor_mode"
        params: Dict[str, Any] = {"reason": reason}
        if activate:
            params["stabilization_time_sec"] = 60

        for sensor_node in sensor_nodes:
            command = {
                "node_uid": sensor_node["node_uid"],
                "channel": "system",
                "cmd": cmd,
                "params": params,
            }
            try:
                await self.command_bus.publish_controller_command(zone_id, command)
            except CircuitBreakerOpenError:
                logger.warning(
                    "Zone %s: API Circuit Breaker is OPEN, skipping sensor mode command",
                    zone_id,
                    extra={"zone_id": zone_id, "cmd": cmd, "node_uid": sensor_node["node_uid"]},
                )
                await self._emit_controller_circuit_open_signal(
                    zone_id,
                    "correction_sensor_mode",
                    channel="system",
                    cmd=cmd,
                )
                return
        self._correction_sensor_mode_state[zone_id] = activate
    
    async def _update_zone_health(self, zone_id: int) -> None:
        """Обновление health score зоны."""
        health_data = await calculate_zone_health(zone_id)
        await update_zone_health_in_db(zone_id, health_data)
    
    async def _check_zone_deletion(self, zone_id: int) -> None:
        """Проверить, не была ли зона удалена, и очистить PID инстансы."""
        try:
            # Проверяем существование зоны через запрос к БД
            from common.db import fetch
            rows = await fetch(
                """
                SELECT id
                FROM zones
                WHERE id = $1
                """,
                zone_id
            )
            
            if not rows:
                # Зона удалена - очищаем PID инстансы
                if zone_id in self.ph_controller._pid_by_zone:
                    del self.ph_controller._pid_by_zone[zone_id]
                    self.ph_controller._last_pid_tick.pop(zone_id, None)
                    logger.info(f"Cleared PH PID instance for deleted zone {zone_id}")
                if zone_id in self.ec_controller._pid_by_zone:
                    del self.ec_controller._pid_by_zone[zone_id]
                    self.ec_controller._last_pid_tick.pop(zone_id, None)
                    logger.info(f"Cleared EC PID instance for deleted zone {zone_id}")
                invalidate_cache(zone_id)
                logger.info(f"Cleared PID cache for deleted zone {zone_id}")
        except Exception as e:
            logger.warning(f"Failed to check zone deletion for zone {zone_id}: {e}", exc_info=True)
            await send_infra_exception_alert(
                error=e,
                code="infra_zone_deletion_check_failed",
                alert_type="Zone Deletion Check Failed",
                severity="warning",
                zone_id=zone_id,
                service="automation-engine",
                component="zone_housekeeping",
                details={"check": "zone_deletion"},
            )
    
    async def _check_pid_config_updates(self, zone_id: int) -> None:
        """Проверить обновления PID конфигов и инвалидировать кеш при необходимости."""
        from common.db import fetch
        
        try:
            # Проверяем последние события PID_CONFIG_UPDATED за последние 2 минуты
            rows = await fetch(
                """
                SELECT details
                FROM zone_events
                WHERE zone_id = $1
                  AND type = 'PID_CONFIG_UPDATED'
                  AND created_at > NOW() - INTERVAL '2 minutes'
                ORDER BY created_at DESC
                LIMIT 1
                """,
                zone_id
            )
            
            if rows:
                # Найдено обновление конфига - инвалидируем кеш
                details = rows[0]['details']
                if isinstance(details, dict):
                    pid_type = details.get('type')
                    if pid_type:
                        invalidate_cache(zone_id, pid_type)
                        logger.info(f"Invalidated PID config cache for zone {zone_id}, type {pid_type}")
                        
                        # Пересоздаем PID-инстанс в контроллерах
                        if pid_type == 'ph' and zone_id in self.ph_controller._pid_by_zone:
                            del self.ph_controller._pid_by_zone[zone_id]
                            self.ph_controller._last_pid_tick.pop(zone_id, None)
                        elif pid_type == 'ec' and zone_id in self.ec_controller._pid_by_zone:
                            del self.ec_controller._pid_by_zone[zone_id]
                            self.ec_controller._last_pid_tick.pop(zone_id, None)
        except Exception as e:
            logger.warning(f"Failed to check PID config updates for zone {zone_id}: {e}", exc_info=True)
            await send_infra_exception_alert(
                error=e,
                code="infra_pid_config_update_check_failed",
                alert_type="PID Config Update Check Failed",
                severity="warning",
                zone_id=zone_id,
                service="automation-engine",
                component="zone_housekeeping",
                details={"check": "pid_config_updates"},
            )
