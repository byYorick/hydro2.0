"""
System State Logger - логирование состояния системы для прозрачности.
"""
import logging
from typing import Dict, Any, Optional, List
from datetime import datetime
from infrastructure.command_tracker import CommandTracker
from services.zone_automation_service import ZoneAutomationService
from infrastructure.circuit_breaker import CircuitBreaker

logger = logging.getLogger(__name__)


async def log_system_state(
    zone_service: Optional[ZoneAutomationService],
    zones: List[Dict[str, Any]],
    command_tracker: Optional[CommandTracker],
    db_circuit_breaker: Optional[CircuitBreaker],
    api_circuit_breaker: Optional[CircuitBreaker],
    mqtt_circuit_breaker: Optional[CircuitBreaker]
) -> None:
    """
    Логировать состояние системы.
    
    Args:
        zone_service: Сервис автоматизации зон
        zones: Список зон
        command_tracker: Трекер команд
        db_circuit_breaker: Circuit Breaker для БД
        api_circuit_breaker: Circuit Breaker для API
        mqtt_circuit_breaker: Circuit Breaker для MQTT
    """
    try:
        state: Dict[str, Any] = {
            'timestamp': datetime.utcnow().isoformat(),
            'zones': {
                'total': len(zones),
                'active': len([z for z in zones if z.get('status') == 'active']),
            }
        }
        
        # PID инстансы
        if zone_service:
            state['pid_instances'] = {
                'ph': len(zone_service.ph_controller._pid_by_zone),
                'ec': len(zone_service.ec_controller._pid_by_zone)
            }
        
        # Ожидающие команды
        if command_tracker:
            pending = await command_tracker.get_pending_commands()
            state['pending_commands'] = {
                'total': len(pending),
                'by_zone': {}
            }
            for cmd_id, cmd_info in pending.items():
                zone_id = cmd_info['zone_id']
                if zone_id not in state['pending_commands']['by_zone']:
                    state['pending_commands']['by_zone'][zone_id] = 0
                state['pending_commands']['by_zone'][zone_id] += 1
        
        # Circuit Breakers
        state['circuit_breakers'] = {}
        if db_circuit_breaker:
            state['circuit_breakers']['database'] = {
                'state': db_circuit_breaker.state.value,
                'failure_count': db_circuit_breaker.failure_count
            }
        if api_circuit_breaker:
            state['circuit_breakers']['api'] = {
                'state': api_circuit_breaker.state.value,
                'failure_count': api_circuit_breaker.failure_count
            }
        if mqtt_circuit_breaker:
            state['circuit_breakers']['mqtt'] = {
                'state': mqtt_circuit_breaker.state.value,
                'failure_count': mqtt_circuit_breaker.failure_count
            }
        
        logger.info("System state", extra=state)
    except Exception as e:
        logger.warning(f"Failed to log system state: {e}", exc_info=True)


