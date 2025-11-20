"""
Correction Controller - универсальный контроллер для корректировки pH и EC.
Устраняет дублирование кода между pH и EC корректировкой.
"""
from typing import Optional, Dict, Any
from enum import Enum
import logging
from common.db import create_zone_event, create_ai_log
from correction_cooldown import should_apply_correction, record_correction

logger = logging.getLogger(__name__)


class CorrectionType(Enum):
    """Тип корректировки."""
    PH = "ph"
    EC = "ec"


class CorrectionController:
    """Универсальный контроллер для корректировки pH/EC."""
    
    def __init__(self, correction_type: CorrectionType):
        """
        Инициализация контроллера.
        
        Args:
            correction_type: Тип корректировки (PH или EC)
        """
        self.correction_type = correction_type
        self.metric_name = correction_type.value.upper()
        self.event_prefix = correction_type.value.upper()
    
    async def check_and_correct(
        self,
        zone_id: int,
        targets: Dict[str, Any],
        telemetry: Dict[str, Optional[float]],
        nodes: Dict[str, Dict[str, Any]],
        water_level_ok: bool
    ) -> Optional[Dict[str, Any]]:
        """
        Проверка и корректировка параметра (pH или EC).
        
        Args:
            zone_id: ID зоны
            targets: Целевые значения из рецепта
            telemetry: Текущие значения телеметрии
            nodes: Узлы зоны
            water_level_ok: Флаг, что уровень воды в норме
        
        Returns:
            Команда для корректировки или None
        """
        target_key = self.correction_type.value
        current = telemetry.get(self.metric_name) or telemetry.get(target_key)
        target = targets.get(target_key)
        
        if target is None or current is None:
            return None
        
        try:
            target_val = float(target)
            current_val = float(current)
        except (ValueError, TypeError) as e:
            logger.warning(f"Zone {zone_id}: Invalid {target_key} values - target={target}, current={current}: {e}")
            return None
        
        diff = current_val - target_val
        
        # Проверяем, превышает ли отклонение порог
        if abs(diff) <= 0.2:
            return None
        
        # Проверяем cooldown и анализ тренда
        should_correct, reason = await should_apply_correction(
            zone_id, target_key, current_val, target_val, diff
        )
        
        if not should_correct:
            logger.info(f"Zone {zone_id}: {self.metric_name} correction skipped - {reason}")
            # Создаем событие о пропуске корректировки
            await create_zone_event(
                zone_id,
                f'{self.event_prefix}_CORRECTION_SKIPPED',
                {
                    f'current_{target_key}': current_val,
                    f'target_{target_key}': target_val,
                    'diff': diff,
                    'reason': reason
                }
            )
            return None
        
        # Проверяем уровень воды перед дозированием
        if not water_level_ok:
            return None
        
        # Находим узел для корректировки
        irrig_node = self._find_irrigation_node(nodes)
        if not irrig_node:
            return None
        
        # Определяем тип корректировки и количество
        correction_type = self._determine_correction_type(diff)
        amount = self._calculate_amount(abs(diff))
        
        # Формируем команду
        command = {
            'node_uid': irrig_node['node_uid'],
            'channel': irrig_node['channel'],
            'cmd': f'adjust_{target_key}',
            'params': {
                'amount': amount,
                'type': correction_type
            },
            'event_type': self._get_correction_event_type(),
            'event_details': {
                'correction_type': correction_type,
                f'current_{target_key}': current_val,
                f'target_{target_key}': target_val,
                'diff': diff,
                'dose_ml': amount
            },
            'zone_id': zone_id,
            'correction_type_str': target_key,
            'current_value': current_val,
            'target_value': target_val,
            'reason': reason
        }
        
        return command
    
    async def apply_correction(
        self,
        command: Dict[str, Any],
        command_bus
    ) -> None:
        """
        Применить корректировку: отправить команду, создать события и логи.
        
        Args:
            command: Команда корректировки (результат check_and_correct)
            command_bus: CommandBus для публикации команд
        """
        zone_id = command['zone_id']
        correction_type_str = command['correction_type_str']
        current_val = command['current_value']
        target_val = command['target_value']
        diff = command['event_details']['diff']
        correction_type = command['event_details']['correction_type']
        reason = command.get('reason', '')
        
        # Отправляем команду через Command Bus
        await command_bus.publish_controller_command(zone_id, command)
        
        # Записываем информацию о корректировке
        await record_correction(zone_id, correction_type_str, {
            "correction_type": correction_type,
            f"current_{correction_type_str}": current_val,
            f"target_{correction_type_str}": target_val,
            "diff": diff,
            "reason": reason
        })
        
        # Создаем основное событие корректировки
        await create_zone_event(
            zone_id,
            command['event_type'],
            command['event_details']
        )
        
        # Создаем событие DOSING для совместимости
        await create_zone_event(
            zone_id,
            'DOSING',
            {
                'type': f'{correction_type_str}_correction',
                'correction_type': correction_type,
                f'current_{correction_type_str}': current_val,
                f'target_{correction_type_str}': target_val,
                'diff': diff
            }
        )
        
        # Для pH создаем дополнительные события при критических отклонениях
        from config.settings import get_settings
        settings = get_settings()
        
        if self.correction_type == CorrectionType.PH:
            if diff > settings.PH_TOO_HIGH_THRESHOLD:
                await create_zone_event(
                    zone_id,
                    'PH_TOO_HIGH_DETECTED',
                    {
                        'current_ph': current_val,
                        'target_ph': target_val,
                        'diff': diff
                    }
                )
            elif diff < settings.PH_TOO_LOW_THRESHOLD:
                await create_zone_event(
                    zone_id,
                    'PH_TOO_LOW_DETECTED',
                    {
                        'current_ph': current_val,
                        'target_ph': target_val,
                        'diff': diff
                    }
                )
        
        # Создаем AI log
        await create_ai_log(
            zone_id,
            'recommend',
            {
                'action': f'{correction_type_str}_correction',
                'metric': correction_type_str,
                'current': current_val,
                'target': target_val,
                'correction': correction_type
            }
        )
    
    def _find_irrigation_node(self, nodes: Dict[str, Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """Найти узел для полива/дозирования."""
        for key, node_info in nodes.items():
            if node_info["type"] == "irrig":
                return node_info
        return None
    
    def _determine_correction_type(self, diff: float) -> str:
        """Определить тип корректировки на основе разницы."""
        from config.settings import get_settings
        settings = get_settings()
        
        threshold = settings.PH_CORRECTION_THRESHOLD if self.correction_type == CorrectionType.PH else settings.EC_CORRECTION_THRESHOLD
        
        if self.correction_type == CorrectionType.PH:
            return "add_base" if diff < -threshold else "add_acid"
        else:  # EC
            return "add_nutrients" if diff < -threshold else "dilute"
    
    def _calculate_amount(self, diff: float) -> float:
        """Рассчитать количество для дозирования."""
        from config.settings import get_settings
        settings = get_settings()
        
        if self.correction_type == CorrectionType.PH:
            return abs(diff) * settings.PH_DOSING_MULTIPLIER
        else:  # EC
            return abs(diff) * settings.EC_DOSING_MULTIPLIER
    
    def _get_correction_event_type(self) -> str:
        """Получить тип события для корректировки."""
        if self.correction_type == CorrectionType.PH:
            return 'PH_CORRECTED'
        else:  # EC
            return 'EC_DOSING'

