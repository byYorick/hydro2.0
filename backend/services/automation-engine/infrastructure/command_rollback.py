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
        params = original_command.get('params', {}) or {}
        correction_type = params.get('type')

        if cmd in ('dose', 'run_pump'):
            # Откат pH: дозируем противоположное вещество с уменьшенной дозой
            if correction_type in ('add_acid', 'add_base'):
                amount = params.get('ml') or params.get('amount') or 0
                duration_ms = params.get('duration_ms')

                rollback_type = 'add_base' if correction_type == 'add_acid' else 'add_acid'
                rollback_params = {'type': rollback_type}

                if amount:
                    rollback_params['ml'] = amount * 0.5
                if duration_ms:
                    rollback_params['duration_ms'] = int(duration_ms * 0.5)

                return {
                    'node_uid': original_command['node_uid'],
                    'channel': original_command.get('channel', 'default'),
                    'cmd': cmd,
                    'params': rollback_params,
                    'event_type': 'PH_ROLLBACK',
                    'event_details': {
                        'original_type': correction_type,
                        'rollback_type': rollback_type,
                        'original_amount': amount,
                        'rollback_amount': amount * 0.5 if amount else None,
                        'original_duration_ms': duration_ms,
                        'rollback_duration_ms': int(duration_ms * 0.5) if duration_ms else None
                    }
                }
            # Для EC откат пока не выполняем
            return None
        
        # Для других команд откат не требуется
        return None
