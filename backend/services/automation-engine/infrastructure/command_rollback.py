"""
Command Rollback - механизм отката команд.
Позволяет отменить команду при обнаружении ошибки.
"""
import json
import logging
from typing import Dict, Any, Optional
from common.db import fetch, create_zone_event
from .command_bus import CommandBus

logger = logging.getLogger(__name__)


class CommandRollback:
    """Механизм отката команд."""
    
    def __init__(self, command_bus: CommandBus):
        """
        Инициализация механизма отката.
        
        Args:
            command_bus: Command Bus для отправки команд отката
        """
        self.command_bus = command_bus
    
    async def rollback_command(self, cmd_id: str) -> bool:
        """
        Откатить команду.
        
        Args:
            cmd_id: ID команды для отката
        
        Returns:
            True если откат выполнен, False в противном случае
        """
        try:
            # Получаем информацию о команде
            rows = await fetch(
                """
                SELECT zone_id, command_data
                FROM command_tracking
                WHERE cmd_id = $1
                """,
                cmd_id
            )
            
            if not rows:
                logger.warning(f"Command {cmd_id} not found for rollback")
                return False
            
            command = rows[0]['command_data']
            zone_id = rows[0]['zone_id']
            
            # Определяем команду отката
            rollback_command = self._create_rollback_command(command)
            
            if rollback_command:
                # Отправляем команду отката
                success = await self.command_bus.publish_controller_command(zone_id, rollback_command)
                
                if success:
                    # Создаем событие
                    await create_zone_event(zone_id, 'COMMAND_ROLLBACK', {
                        'original_cmd_id': cmd_id,
                        'rollback_command': rollback_command
                    })
                    
                    logger.info(
                        f"Zone {zone_id}: Command {cmd_id} rolled back",
                        extra={'zone_id': zone_id, 'cmd_id': cmd_id}
                    )
                    return True
                else:
                    logger.error(f"Zone {zone_id}: Failed to send rollback command for {cmd_id}")
                    return False
            else:
                logger.warning(f"Zone {zone_id}: No rollback command for {cmd_id}")
                return False
                
        except Exception as e:
            logger.error(
                f"Failed to rollback command {cmd_id}: {e}",
                exc_info=True
            )
            return False
    
    def _create_rollback_command(self, original_command: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Создать команду отката.
        
        Args:
            original_command: Исходная команда
        
        Returns:
            Команда отката или None
        """
        import json
        if isinstance(original_command, str):
            original_command = json.loads(original_command)
        
        cmd = original_command.get('cmd')
        
        if cmd == 'adjust_ph':
            # Откат: дозируем противоположное вещество с уменьшенной дозой
            params = original_command.get('params', {})
            original_type = params.get('type')
            amount = params.get('amount', 0)
            
            if original_type == 'add_acid':
                rollback_type = 'add_base'
            elif original_type == 'add_base':
                rollback_type = 'add_acid'
            else:
                return None
            
            return {
                'node_uid': original_command['node_uid'],
                'channel': original_command['channel'],
                'cmd': 'adjust_ph',
                'params': {
                    'amount': amount * 0.5,  # 50% откат
                    'type': rollback_type
                },
                'event_type': 'PH_ROLLBACK',
                'event_details': {
                    'original_type': original_type,
                    'rollback_type': rollback_type,
                    'original_amount': amount,
                    'rollback_amount': amount * 0.5
                }
            }
        
        elif cmd == 'adjust_ec':
            # Откат для EC сложнее, так как нужно знать, что было добавлено
            # Для простоты не делаем откат для EC
            return None
        
        # Для других команд откат не требуется
        return None

