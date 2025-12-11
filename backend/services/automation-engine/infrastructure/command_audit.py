"""
Command Audit - полный аудит всех команд для прозрачности системы.
Записывает каждую команду с контекстом принятия решения.
"""
import json
import logging
from typing import Dict, Any, Optional
from datetime import datetime
from common.db import execute

logger = logging.getLogger(__name__)


class CommandAudit:
    """Аудит всех команд системы."""
    
    async def audit_command(
        self,
        zone_id: int,
        command: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        Записать команду в аудит.
        
        Args:
            zone_id: ID зоны
            command: Команда
            context: Контекст принятия решения (телеметрия, PID состояние, причина)
        """
        try:
            command_type = command.get('cmd', 'unknown')
            
            # Извлекаем контекст
            telemetry_snapshot = context.get('telemetry', {}) if context else {}
            decision_context = {
                'current_value': context.get('current_value'),
                'target_value': context.get('target_value'),
                'diff': context.get('diff'),
                'reason': context.get('reason'),
                'pid_zone': context.get('pid_zone'),
                'pid_output': context.get('pid_output'),
                'pid_integral': context.get('pid_integral'),
            } if context else {}
            
            pid_state = {
                'integral': context.get('pid_integral'),
                'prev_error': context.get('pid_prev_error'),
                'zone': context.get('pid_zone'),
            } if context else {}
            
            await execute(
                """
                INSERT INTO command_audit (
                    zone_id, command_type, command_data,
                    telemetry_snapshot, decision_context, pid_state, created_at
                )
                VALUES ($1, $2, $3, $4, $5, $6, NOW())
                """,
                zone_id,
                command_type,
                json.dumps(command),
                json.dumps(telemetry_snapshot) if telemetry_snapshot else None,
                json.dumps(decision_context) if decision_context else None,
                json.dumps(pid_state) if pid_state else None
            )
            
            logger.debug(
                f"Zone {zone_id}: Command audited",
                extra={
                    'zone_id': zone_id,
                    'command_type': command_type,
                    'trace_id': context.get('trace_id') if context else None
                }
            )
        except Exception as e:
            # Не прерываем выполнение при ошибке аудита
            logger.warning(
                f"Zone {zone_id}: Failed to audit command: {e}",
                exc_info=True,
                extra={'zone_id': zone_id, 'command': command}
            )


