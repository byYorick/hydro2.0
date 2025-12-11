"""
Валидация команд перед отправкой.
Предотвращает отправку некорректных команд, которые могут навредить системе.
"""
import logging
from typing import Dict, Any, Tuple, Optional
from config.settings import get_settings

logger = logging.getLogger(__name__)


class CommandValidator:
    """Валидатор команд для автоматизации."""
    
    def __init__(self):
        self.settings = get_settings()
    
    def validate_correction_command(self, command: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        """
        Валидация команды корректировки pH/EC.
        
        Args:
            command: Команда для валидации
        
        Returns:
            Tuple[is_valid, error_message]
        """
        # Проверка обязательных полей
        required_fields = ['node_uid', 'channel', 'cmd', 'params']
        for field in required_fields:
            if field not in command:
                return False, f"Missing required field: {field}"
        
        # Проверка типа команды
        cmd = command.get('cmd')
        if cmd not in ['adjust_ph', 'adjust_ec']:
            return False, f"Invalid command type: {cmd}"
        
        # Проверка параметров
        params = command.get('params', {})
        if not isinstance(params, dict):
            return False, "Params must be a dictionary"
        
        amount = params.get('amount')
        if amount is None:
            return False, "Missing 'amount' in params"
        
        try:
            amount = float(amount)
        except (ValueError, TypeError):
            return False, f"Invalid amount type: {amount}"
        
        if amount <= 0:
            return False, f"Amount must be positive, got {amount}"
        
        # Максимальная доза зависит от типа
        max_amount = self.settings.PH_PID_MAX_OUTPUT if cmd == 'adjust_ph' else self.settings.EC_PID_MAX_OUTPUT
        if amount > max_amount:
            return False, f"Amount too high: {amount}ml (max: {max_amount}ml)"
        
        # Проверка типа корректировки
        correction_type = params.get('type')
        valid_types = ['add_acid', 'add_base', 'add_nutrients', 'dilute']
        if correction_type not in valid_types:
            return False, f"Invalid correction type: {correction_type}. Valid: {valid_types}"
        
        # Проверка соответствия типа команде
        if cmd == 'adjust_ph' and correction_type not in ['add_acid', 'add_base']:
            return False, f"Invalid correction type for pH: {correction_type}"
        if cmd == 'adjust_ec' and correction_type not in ['add_nutrients', 'dilute']:
            return False, f"Invalid correction type for EC: {correction_type}"
        
        return True, None
    
    def validate_irrigation_command(self, command: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        """
        Валидация команды полива.
        
        Args:
            command: Команда для валидации
        
        Returns:
            Tuple[is_valid, error_message]
        """
        # Проверка обязательных полей
        if 'node_uid' not in command:
            return False, "Missing required field: node_uid"
        if 'cmd' not in command or command['cmd'] != 'irrigate':
            return False, "Invalid command type for irrigation"
        
        # Проверка параметров
        params = command.get('params', {})
        if not isinstance(params, dict):
            return False, "Params must be a dictionary"
        
        duration = params.get('duration_sec')
        if duration is None:
            return False, "Missing 'duration_sec' in params"
        
        try:
            duration = int(duration)
        except (ValueError, TypeError):
            return False, f"Invalid duration type: {duration}"
        
        if duration <= 0:
            return False, f"Duration must be positive, got {duration}"
        
        # Максимальная длительность полива: 1 час
        if duration > 3600:
            return False, f"Duration too long: {duration}s (max: 3600s)"
        
        return True, None
    
    def validate_recirculation_command(self, command: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        """
        Валидация команды рециркуляции.
        
        Args:
            command: Команда для валидации
        
        Returns:
            Tuple[is_valid, error_message]
        """
        # Проверка обязательных полей
        if 'node_uid' not in command:
            return False, "Missing required field: node_uid"
        if 'cmd' not in command or command['cmd'] != 'recirculate':
            return False, "Invalid command type for recirculation"
        
        # Проверка параметров
        params = command.get('params', {})
        if not isinstance(params, dict):
            return False, "Params must be a dictionary"
        
        duration = params.get('duration_sec')
        if duration is None:
            return False, "Missing 'duration_sec' in params"
        
        try:
            duration = int(duration)
        except (ValueError, TypeError):
            return False, f"Invalid duration type: {duration}"
        
        if duration <= 0:
            return False, f"Duration must be positive, got {duration}"
        
        # Максимальная длительность рециркуляции: 30 минут
        if duration > 1800:
            return False, f"Duration too long: {duration}s (max: 1800s)"
        
        return True, None
    
    def validate_climate_command(self, command: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        """
        Валидация команды управления климатом.
        
        Args:
            command: Команда для валидации
        
        Returns:
            Tuple[is_valid, error_message]
        """
        # Проверка обязательных полей
        if 'node_uid' not in command:
            return False, "Missing required field: node_uid"
        if 'cmd' not in command or command['cmd'] != 'set_relay':
            return False, "Invalid command type for climate"
        
        # Проверка параметров
        params = command.get('params', {})
        if not isinstance(params, dict):
            return False, "Params must be a dictionary"
        
        state = params.get('state')
        if state is None:
            return False, "Missing 'state' in params"
        
        if not isinstance(state, bool):
            return False, f"State must be boolean, got {type(state)}"
        
        return True, None
    
    def validate_light_command(self, command: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        """
        Валидация команды управления освещением.
        
        Args:
            command: Команда для валидации
        
        Returns:
            Tuple[is_valid, error_message]
        """
        # Проверка обязательных полей
        if 'node_uid' not in command:
            return False, "Missing required field: node_uid"
        
        cmd = command.get('cmd')
        if cmd not in ['set_light', 'set_relay']:
            return False, f"Invalid command type for light: {cmd}"
        
        # Проверка параметров
        params = command.get('params', {})
        if not isinstance(params, dict):
            return False, "Params must be a dictionary"
        
        if cmd == 'set_light':
            intensity = params.get('intensity')
            if intensity is None:
                return False, "Missing 'intensity' in params"
            
            try:
                intensity = int(intensity)
            except (ValueError, TypeError):
                return False, f"Invalid intensity type: {intensity}"
            
            if intensity < 0 or intensity > 100:
                return False, f"Intensity must be 0-100, got {intensity}"
        
        elif cmd == 'set_relay':
            state = params.get('state')
            if state is None:
                return False, "Missing 'state' in params"
            
            if not isinstance(state, bool):
                return False, f"State must be boolean, got {type(state)}"
        
        return True, None
    
    def validate_command(self, command: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        """
        Универсальная валидация команды.
        
        Args:
            command: Команда для валидации
        
        Returns:
            Tuple[is_valid, error_message]
        """
        if not isinstance(command, dict):
            return False, "Command must be a dictionary"
        
        cmd = command.get('cmd', '')
        
        # Выбираем валидатор по типу команды
        if cmd.startswith('adjust_'):
            return self.validate_correction_command(command)
        elif cmd == 'irrigate':
            return self.validate_irrigation_command(command)
        elif cmd == 'recirculate':
            return self.validate_recirculation_command(command)
        elif cmd == 'set_relay':
            # Может быть климат или свет
            event_type = command.get('event_type', '')
            if 'CLIMATE' in event_type:
                return self.validate_climate_command(command)
            elif 'LIGHT' in event_type:
                return self.validate_light_command(command)
            # По умолчанию проверяем как климат
            return self.validate_climate_command(command)
        elif cmd == 'set_light':
            return self.validate_light_command(command)
        else:
            # Для неизвестных команд проверяем базовую структуру
            if 'node_uid' not in command:
                return False, "Missing required field: node_uid"
            if 'cmd' not in command:
                return False, "Missing required field: cmd"
            return True, None


