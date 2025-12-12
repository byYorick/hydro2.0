"""
Zone Automation Service - оркестрация обработки зоны.
Изолирует бизнес-логику от инфраструктуры.
"""
from typing import Dict, Any, Optional
import logging
from datetime import datetime, timedelta
from common.utils.time import utcnow
from common.db import create_zone_event
from common.water_flow import check_water_level, ensure_water_level_alert
from common.pump_safety import can_run_pump
from recipe_utils import calculate_current_phase, advance_phase
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
        
        # Инициализация контроллеров корректировки с менеджером состояния
        self.ph_controller = CorrectionController(CorrectionType.PH, self.pid_state_manager)
        self.ec_controller = CorrectionController(CorrectionType.EC, self.pid_state_manager)
        
        # Circuit breaker: отслеживание последних ошибок контроллеров
        # Ключ: (zone_id, controller_name), значение: datetime последней ошибки
        self._controller_failures: Dict[tuple[int, str], datetime] = {}
        
        # Per-zone state для backoff и degraded mode
        # Ключ: zone_id, значение: {'error_streak': int, 'next_allowed_run_at': datetime}
        self._zone_states: Dict[int, Dict[str, Any]] = {}
    
    async def save_all_pid_states(self):
        """Сохранить состояние всех PID контроллеров."""
        await self.ph_controller.save_all_states()
        await self.ec_controller.save_all_states()
    
    async def process_zone(self, zone_id: int) -> None:
        """
        Оркестрация одного цикла обработки зоны с поддержкой backoff и degraded mode.
        
        Args:
            zone_id: ID зоны для обработки
        """
        # Проверка backoff - пропускаем зону, если еще не прошло время
        if not self._should_process_zone(zone_id):
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
                await self._check_phase_transitions(zone_id)
            
            # Получение данных зоны через circuit breaker
            try:
                # Получаем активный grow_cycle (приоритет над zone_recipe_instance)
                grow_cycle = await self.grow_cycle_repo.get_active_grow_cycle(zone_id)
                
                # Получаем targets из grow_cycle или fallback на zone_recipe_instance
                targets = None
                if grow_cycle and grow_cycle.get("targets"):
                    targets = grow_cycle["targets"]
                else:
                    # Fallback: используем старый способ через zone_recipe_instance
                    zone_data = await self.recipe_repo.get_zone_data_batch(zone_id)
                    recipe_info = zone_data.get("recipe_info")
                    if recipe_info and recipe_info.get("targets"):
                        targets = recipe_info["targets"]
                
                if not targets or not isinstance(targets, dict):
                    return
                
                # Получаем телеметрию и capabilities
                zone_data = await self.recipe_repo.get_zone_data_batch(zone_id)
                telemetry = zone_data.get("telemetry", {})
                telemetry_timestamps = zone_data.get("telemetry_timestamps", {})
                nodes = zone_data.get("nodes", {})
                capabilities = zone_data.get("capabilities", {})
                
                # Получаем bindings для зоны
                bindings = await self.infrastructure_repo.get_zone_bindings_by_role(zone_id)
            except CircuitBreakerOpenError:
                # Circuit breaker открыт - переходим в спокойный режим
                logger.warning(
                    f"Zone {zone_id}: Database Circuit Breaker is OPEN, skipping zone processing",
                    extra={"zone_id": zone_id}
                )
                self._record_zone_error(zone_id)
                return
            
            # Сохраняем telemetry_timestamps для использования в _process_correction_controllers
            self._current_telemetry_timestamps = telemetry_timestamps
            
            # Проверка уровня воды (safety check, всегда выполняется)
            water_level_ok, water_level = await check_water_level(zone_id)
            if water_level is not None:
                await ensure_water_level_alert(zone_id, water_level)
            
            # В degraded mode выполняем только safety checks + health + стоп-условия
            if is_degraded:
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
                self._reset_zone_error_streak(zone_id)
                return
            
            # Нормальный режим - выполняем все контроллеры
            # Обработка контроллеров в правильном порядке с изоляцией ошибок
            # 1. Light Controller
            await self._safe_process_controller(
                'light',
                self._process_light_controller(zone_id, targets, capabilities, bindings),
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
                self._process_irrigation_controller(zone_id, targets, telemetry, capabilities, water_level_ok, bindings),
                zone_id
            )
            
            # 4. Recirculation Controller
            await self._safe_process_controller(
                'recirculation',
                self._process_recirculation_controller(zone_id, targets, telemetry, capabilities, water_level_ok, bindings),
                zone_id
            )
            
            # 5. pH/EC Correction Controllers
            await self._safe_process_controller(
                'correction',
                self._process_correction_controllers(zone_id, targets, telemetry, nodes, capabilities, water_level_ok),
                zone_id
            )
            
            # 6. Zone Health Monitor
            await self._safe_process_controller(
                'health',
                self._update_zone_health(zone_id),
                zone_id
            )
            
            # Успешное выполнение - сбрасываем error_streak
            self._reset_zone_error_streak(zone_id)
            
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
        if zone_id not in self._zone_states:
            self._zone_states[zone_id] = {
                'error_streak': 0,
                'next_allowed_run_at': None
            }
        return self._zone_states[zone_id]
    
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
    
    def _reset_zone_error_streak(self, zone_id: int) -> None:
        """
        Сбросить error_streak для зоны после успешного выполнения.
        
        Args:
            zone_id: ID зоны
        """
        state = self._get_zone_state(zone_id)
        if state['error_streak'] > 0:
            logger.info(
                f"Zone {zone_id}: Resetting error_streak (was {state['error_streak']}) after successful cycle",
                extra={'zone_id': zone_id, 'previous_error_streak': state['error_streak']}
            )
        
        state['error_streak'] = 0
        state['next_allowed_run_at'] = None
    
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
    
    async def _safe_process_controller(
        self,
        controller_name: str,
        controller_coro,
        zone_id: int
    ) -> None:
        """
        Безопасное выполнение контроллера с изоляцией ошибок.
        
        Args:
            controller_name: Имя контроллера для логирования
            controller_coro: Корутина контроллера (awaitable)
            zone_id: ID зоны
        """
        # Проверяем cooldown
        if self._is_controller_in_cooldown(zone_id, controller_name):
            logger.debug(
                f"Zone {zone_id}: Controller '{controller_name}' is in cooldown, skipping",
                extra={'zone_id': zone_id, 'controller': controller_name}
            )
            return
        
        try:
            await controller_coro
            # Если выполнение успешно, очищаем запись об ошибке (если была)
            key = (zone_id, controller_name)
            if key in self._controller_failures:
                del self._controller_failures[key]
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
    
    async def _check_phase_transitions(self, zone_id: int) -> None:
        """Проверка и переход между фазами рецепта."""
        phase_calc = await calculate_current_phase(zone_id)
        if not phase_calc:
            return
        
        if phase_calc.get("should_transition") and phase_calc["target_phase_index"] > phase_calc["phase_index"]:
            new_phase_index = phase_calc["target_phase_index"]
            success = await advance_phase(zone_id, new_phase_index)
            if success:
                await create_zone_event(
                    zone_id,
                    'PHASE_TRANSITION',
                    {
                        'from_phase': phase_calc["phase_index"],
                        'to_phase': new_phase_index
                    }
                )
    
    async def _process_light_controller(
        self,
        zone_id: int,
        targets: Dict[str, Any],
        capabilities: Dict[str, bool],
        bindings: Dict[str, Dict[str, Any]]
    ) -> None:
        """Обработка контроллера освещения."""
        if not capabilities.get("light_control", False):
            return
        
        light_cmd = await check_and_control_lighting(zone_id, targets, bindings, utcnow())
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
                break  # Прерываем цикл при открытом circuit breaker
    
    async def _process_irrigation_controller(
        self,
        zone_id: int,
        targets: Dict[str, Any],
        telemetry: Dict[str, Optional[float]],
        capabilities: Dict[str, bool],
        water_level_ok: bool,
        bindings: Dict[str, Dict[str, Any]]
    ) -> None:
        """Обработка контроллера полива."""
        if not capabilities.get("irrigation_control", False):
            return
        
        irrigation_cmd = await check_and_control_irrigation(zone_id, targets, telemetry, bindings)
        
        # Проверка безопасности перед запуском насоса
        if irrigation_cmd:
            pump_channel = irrigation_cmd.get('channel', 'default')
            can_run, error_msg = await can_run_pump(zone_id, pump_channel)
            if not can_run:
                logger.warning(f"Zone {zone_id}: Cannot run irrigation pump {pump_channel}: {error_msg}")
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
    
    async def _process_recirculation_controller(
        self,
        zone_id: int,
        targets: Dict[str, Any],
        telemetry: Dict[str, Optional[float]],
        capabilities: Dict[str, bool],
        water_level_ok: bool,
        bindings: Dict[str, Dict[str, Any]]
    ) -> None:
        """Обработка контроллера рециркуляции."""
        if not capabilities.get("recirculation", False):
            return
        
        recirculation_cmd = await check_and_control_recirculation(zone_id, targets, telemetry, bindings)
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
    
    async def _process_correction_controllers(
        self,
        zone_id: int,
        targets: Dict[str, Any],
        telemetry: Dict[str, Optional[float]],
        nodes: Dict[str, Dict[str, Any]],
        capabilities: Dict[str, bool],
        water_level_ok: bool
    ) -> None:
        """Обработка контроллеров корректировки pH/EC."""
        # Получаем telemetry_timestamps из zone_data (передается через process_zone)
        telemetry_timestamps = getattr(self, '_current_telemetry_timestamps', {})
        
        # pH Correction
        if capabilities.get("ph_control", False):
            ph_cmd = await self.ph_controller.check_and_correct(
                zone_id, targets, telemetry, telemetry_timestamps, nodes, water_level_ok
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
        
        # EC Correction
        if capabilities.get("ec_control", False):
            ec_cmd = await self.ec_controller.check_and_correct(
                zone_id, targets, telemetry, telemetry_timestamps, nodes, water_level_ok
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

