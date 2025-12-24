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
        
        cmd = command.get('cmd')
        if cmd not in ['dose', 'run_pump']:
            return False, f"Invalid command type for correction: {cmd}"
        
        # Проверка параметров
        params = command.get('params', {})
        if not isinstance(params, dict):
            return False, "Params must be a dictionary"
        
        amount = params.get('dose_ml') or params.get('amount')
        if amount is not None:
            try:
                amount = float(amount)
            except (ValueError, TypeError):
                return False, f"Invalid amount type: {amount}"
            if amount <= 0:
                return False, f"Amount must be positive, got {amount}"
            # Максимальная доза зависит от типа
            max_amount = self.settings.PH_PID_MAX_OUTPUT if params.get('type') in ['add_acid', 'add_base'] else self.settings.EC_PID_MAX_OUTPUT
            if amount > max_amount:
                return False, f"Amount too high: {amount}ml (max: {max_amount}ml)"

        # Проверка типа корректировки
        correction_type = params.get('type')
        valid_types = ['add_acid', 'add_base', 'add_nutrients', 'dilute']
        if correction_type not in valid_types:
            return False, f"Invalid correction type: {correction_type}. Valid: {valid_types}"
        
        # Проверка соответствия типа команде
        if correction_type in ['add_acid', 'add_base'] and self.settings.PH_PID_MAX_OUTPUT <= 0:
            return False, "PH PID max output is not configured"
        if correction_type in ['add_nutrients', 'dilute'] and self.settings.EC_PID_MAX_OUTPUT <= 0:
            return False, "EC PID max output is not configured"

        if correction_type in ['add_acid', 'add_base'] and cmd not in ['dose', 'run_pump']:
            return False, f"Invalid correction type for pH: {correction_type}"
        if correction_type in ['add_nutrients', 'dilute'] and cmd not in ['dose', 'run_pump']:
            return False, f"Invalid correction type for EC: {correction_type}"

        # Если используем run_pump, валидируем длительность
        if cmd == 'run_pump':
            duration_ms = params.get('duration_ms')
            if duration_ms is None:
                return False, "Missing 'duration_ms' in params for run_pump"
            try:
                duration_ms = int(duration_ms)
            except (ValueError, TypeError):
                return False, f"Invalid duration_ms type: {duration_ms}"
            if duration_ms <= 0:
                return False, f"Duration must be positive, got {duration_ms}"
        
        return True, None
    
    def validate_run_pump_command(self, command: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        """Валидация команды run_pump (ирригация/рециркуляция/дозирование)."""
        if 'node_uid' not in command:
            return False, "Missing required field: node_uid"
        if command.get('cmd') != 'run_pump':
            return False, "Invalid command type, expected run_pump"

        params = command.get('params', {})
        if not isinstance(params, dict):
            return False, "Params must be a dictionary"

        duration_ms = params.get('duration_ms')
        if duration_ms is None:
            return False, "Missing 'duration_ms' in params"
        try:
            duration_ms = int(duration_ms)
        except (ValueError, TypeError):
            return False, f"Invalid duration_ms type: {duration_ms}"
        if duration_ms <= 0:
            return False, f"Duration must be positive, got {duration_ms}"
        # Жесткий лимит: не больше 1 часа работы
        if duration_ms > 3_600_000:
            return False, f"Duration too long: {duration_ms}ms (max: 3600000ms)"

        # При наличии correction type проверяем допустимость
        if 'type' in params:
            valid_types = ['add_acid', 'add_base', 'add_nutrients', 'dilute']
            if params['type'] not in valid_types:
                return False, f"Invalid correction type: {params['type']}"

        return True, None

    def validate_dose_command(self, command: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        """Валидация dose (ph/ec насосы)."""
        if 'node_uid' not in command:
            return False, "Missing required field: node_uid"
        if command.get('cmd') != 'dose':
            return False, "Invalid command type, expected dose"

        params = command.get('params', {})
        if not isinstance(params, dict):
            return False, "Params must be a dictionary"

        dose_ml = params.get('dose_ml') or params.get('amount')
        if dose_ml is None:
            return False, "Missing 'dose_ml' in params"
        try:
            dose_ml = float(dose_ml)
        except (ValueError, TypeError):
            return False, f"Invalid dose_ml type: {dose_ml}"
        if dose_ml <= 0:
            return False, f"Dose must be positive, got {dose_ml}"

        if 'type' in params:
            valid_types = ['add_acid', 'add_base', 'add_nutrients', 'dilute']
            if params['type'] not in valid_types:
                return False, f"Invalid correction type: {params['type']}"

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
        if cmd in ['dose']:
            return self.validate_dose_command(command)
        elif cmd == 'run_pump':
            # Если передан correction type, валидируем как корректировку
            params = command.get('params', {})
            if isinstance(params, dict) and params.get('type') in ['add_acid', 'add_base', 'add_nutrients', 'dilute']:
                return self.validate_correction_command(command)
            return self.validate_run_pump_command(command)
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

