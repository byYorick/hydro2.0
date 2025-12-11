"""
Zone Automation Service - оркестрация обработки зоны.
Изолирует бизнес-логику от инфраструктуры.
"""
from typing import Dict, Any, Optional
import logging
from datetime import datetime
from common.db import create_zone_event
from common.water_flow import check_water_level, ensure_water_level_alert
from common.pump_safety import can_run_pump
from recipe_utils import calculate_current_phase, advance_phase
from light_controller import check_and_control_lighting
from climate_controller import check_and_control_climate
from irrigation_controller import check_and_control_irrigation, check_and_control_recirculation
from health_monitor import calculate_zone_health, update_zone_health_in_db
from correction_controller import CorrectionController, CorrectionType
from repositories import ZoneRepository, TelemetryRepository, NodeRepository, RecipeRepository
from infrastructure.command_bus import CommandBus
from services.pid_state_manager import PidStateManager
from prometheus_client import Histogram, Counter
from services.pid_config_service import invalidate_cache

logger = logging.getLogger(__name__)

# Метрики для отслеживания производительности
ZONE_CHECKS = Counter("zone_checks_total", "Zone automation checks")
CHECK_LAT = Histogram("zone_check_seconds", "Zone check duration seconds")


class ZoneAutomationService:
    """Сервис для оркестрации автоматизации зоны."""
    
    def __init__(
        self,
        zone_repo: ZoneRepository,
        telemetry_repo: TelemetryRepository,
        node_repo: NodeRepository,
        recipe_repo: RecipeRepository,
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
            command_bus: Command Bus для публикации команд
            pid_state_manager: Менеджер состояния PID (опционально)
        """
        self.zone_repo = zone_repo
        self.telemetry_repo = telemetry_repo
        self.node_repo = node_repo
        self.recipe_repo = recipe_repo
        self.command_bus = command_bus
        self.pid_state_manager = pid_state_manager or PidStateManager()
        
        # Инициализация контроллеров корректировки с менеджером состояния
        self.ph_controller = CorrectionController(CorrectionType.PH, self.pid_state_manager)
        self.ec_controller = CorrectionController(CorrectionType.EC, self.pid_state_manager)
    
    async def save_all_pid_states(self):
        """Сохранить состояние всех PID контроллеров."""
        await self.ph_controller.save_all_states()
        await self.ec_controller.save_all_states()
    
    async def process_zone(self, zone_id: int) -> None:
        """
        Оркестрация одного цикла обработки зоны.
        
        Args:
            zone_id: ID зоны для обработки
        """
        with CHECK_LAT.time():
            ZONE_CHECKS.inc()
            
            # Проверка удаления зоны и очистка PID инстансов
            await self._check_zone_deletion(zone_id)
            
            # Проверка обновлений PID конфигов
            await self._check_pid_config_updates(zone_id)
            
            # Проверка переходов фаз
            await self._check_phase_transitions(zone_id)
        
        # Получение данных зоны
        zone_data = await self.recipe_repo.get_zone_data_batch(zone_id)
        
        recipe_info = zone_data.get("recipe_info")
        if not recipe_info or not recipe_info.get("targets"):
            return
        
        targets = recipe_info["targets"]
        if not isinstance(targets, dict):
            return
        
        # Получаем данные из batch запроса
        telemetry = zone_data.get("telemetry", {})
        telemetry_timestamps = zone_data.get("telemetry_timestamps", {})  # Временные метки для проверки свежести
        nodes = zone_data.get("nodes", {})
        capabilities = zone_data.get("capabilities", {})
        
        # Сохраняем telemetry_timestamps для использования в _process_correction_controllers
        self._current_telemetry_timestamps = telemetry_timestamps
        
        # Проверка уровня воды
        water_level_ok, water_level = await check_water_level(zone_id)
        if water_level is not None:
            await ensure_water_level_alert(zone_id, water_level)
        
        # Обработка контроллеров в правильном порядке
        # 1. Light Controller
        await self._process_light_controller(zone_id, targets, capabilities)
        
        # 2. Climate Controller
        await self._process_climate_controller(zone_id, targets, telemetry, capabilities)
        
        # 3. Irrigation Controller
        await self._process_irrigation_controller(zone_id, targets, telemetry, capabilities, water_level_ok)
        
        # 4. Recirculation Controller
        await self._process_recirculation_controller(zone_id, targets, telemetry, capabilities, water_level_ok)
        
        # 5. pH/EC Correction Controllers
        await self._process_correction_controllers(zone_id, targets, telemetry, nodes, capabilities, water_level_ok)
        
        # 6. Zone Health Monitor
        await self._update_zone_health(zone_id)
    
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
        capabilities: Dict[str, bool]
    ) -> None:
        """Обработка контроллера освещения."""
        if not capabilities.get("light_control", False):
            return
        
        light_cmd = await check_and_control_lighting(zone_id, targets, datetime.now())
        if light_cmd:
            if light_cmd.get('event_type'):
                await create_zone_event(zone_id, light_cmd['event_type'], light_cmd.get('event_details', {}))
            await self.command_bus.publish_controller_command(zone_id, light_cmd)
    
    async def _process_climate_controller(
        self,
        zone_id: int,
        targets: Dict[str, Any],
        telemetry: Dict[str, Optional[float]],
        capabilities: Dict[str, bool]
    ) -> None:
        """Обработка контроллера климата."""
        if not capabilities.get("climate_control", False):
            return
        
        climate_commands = await check_and_control_climate(zone_id, targets, telemetry)
        for cmd in climate_commands:
            if cmd.get('event_type'):
                await create_zone_event(zone_id, cmd['event_type'], cmd.get('event_details', {}))
            await self.command_bus.publish_controller_command(zone_id, cmd)
    
    async def _process_irrigation_controller(
        self,
        zone_id: int,
        targets: Dict[str, Any],
        telemetry: Dict[str, Optional[float]],
        capabilities: Dict[str, bool],
        water_level_ok: bool
    ) -> None:
        """Обработка контроллера полива."""
        if not capabilities.get("irrigation_control", False):
            return
        
        irrigation_cmd = await check_and_control_irrigation(zone_id, targets, telemetry)
        
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
            await self.command_bus.publish_controller_command(zone_id, irrigation_cmd)
    
    async def _process_recirculation_controller(
        self,
        zone_id: int,
        targets: Dict[str, Any],
        telemetry: Dict[str, Optional[float]],
        capabilities: Dict[str, bool],
        water_level_ok: bool
    ) -> None:
        """Обработка контроллера рециркуляции."""
        if not capabilities.get("recirculation", False):
            return
        
        recirculation_cmd = await check_and_control_recirculation(zone_id, targets, telemetry)
        if recirculation_cmd:
            if recirculation_cmd.get('event_type'):
                await create_zone_event(zone_id, recirculation_cmd['event_type'], recirculation_cmd.get('event_details', {}))
            await self.command_bus.publish_controller_command(zone_id, recirculation_cmd)
    
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
                await self.ph_controller.apply_correction(ph_cmd, self.command_bus, pid)
        
        # EC Correction
        if capabilities.get("ec_control", False):
            ec_cmd = await self.ec_controller.check_and_correct(
                zone_id, targets, telemetry, telemetry_timestamps, nodes, water_level_ok
            )
            if ec_cmd:
                # Получаем PID для контекста
                pid = self.ec_controller._pid_by_zone.get(zone_id)
                await self.ec_controller.apply_correction(ec_cmd, self.command_bus, pid)
    
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

