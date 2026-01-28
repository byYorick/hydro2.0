"""
Единый генератор MQTT топиков для node-sim.

Этот модуль является единственным источником истины для формирования MQTT топиков
в системе node-sim. Все модули должны использовать функции из этого модуля
для генерации топиков, чтобы исключить рассинхрон между симулятором и системой.

Формат топиков соответствует спецификации MQTT_NAMESPACE.md и MQTT_SPEC_FULL.md:
- Основной формат: hydro/{gh}/{zone}/{node}/{channel}/{message_type}
- Временные топики (preconfig): hydro/gh-temp/zn-temp/{identifier}/{channel}/{message_type}
"""


def telemetry(gh: str, zone: str, node: str, ch: str) -> str:
    """
    Генерирует топик для телеметрии.
    
    Args:
        gh: UID теплицы (greenhouses.uid)
        zone: UID зоны (zones.uid)
        node: UID узла (nodes.uid)
        ch: Имя канала (channels.key)
    
    Returns:
        Топик в формате: hydro/{gh}/{zone}/{node}/{ch}/telemetry
    
    Example:
        >>> telemetry("gh-1", "zn-1", "nd-ph-1", "ph_sensor")
        'hydro/gh-1/zn-1/nd-ph-1/ph_sensor/telemetry'
    """
    return f"hydro/{gh}/{zone}/{node}/{ch}/telemetry"


def command(gh: str, zone: str, node: str, ch: str) -> str:
    """
    Генерирует топик для команд.
    
    Args:
        gh: UID теплицы (greenhouses.uid)
        zone: UID зоны (zones.uid)
        node: UID узла (nodes.uid)
        ch: Имя канала (channels.key)
    
    Returns:
        Топик в формате: hydro/{gh}/{zone}/{node}/{ch}/command
    
    Example:
        >>> command("gh-1", "zn-1", "nd-ph-1", "pump_acid")
        'hydro/gh-1/zn-1/nd-ph-1/pump_acid/command'
    """
    return f"hydro/{gh}/{zone}/{node}/{ch}/command"


def command_response(gh: str, zone: str, node: str, ch: str) -> str:
    """
    Генерирует топик для ответов на команды.
    
    Args:
        gh: UID теплицы (greenhouses.uid)
        zone: UID зоны (zones.uid)
        node: UID узла (nodes.uid)
        ch: Имя канала (channels.key)
    
    Returns:
        Топик в формате: hydro/{gh}/{zone}/{node}/{ch}/command_response
    
    Example:
        >>> command_response("gh-1", "zn-1", "nd-ph-1", "pump_acid")
        'hydro/gh-1/zn-1/nd-ph-1/pump_acid/command_response'
    """
    return f"hydro/{gh}/{zone}/{node}/{ch}/command_response"


def error(gh: str, zone: str, node: str) -> str:
    """
    Генерирует топик для ошибок узла.
    
    Args:
        gh: UID теплицы (greenhouses.uid)
        zone: UID зоны (zones.uid)
        node: UID узла (nodes.uid)
    
    Returns:
        Топик в формате: hydro/{gh}/{zone}/{node}/error
    
    Example:
        >>> error("gh-1", "zn-1", "nd-ph-1")
        'hydro/gh-1/zn-1/nd-ph-1/error'
    """
    return f"hydro/{gh}/{zone}/{node}/error"


def status(gh: str, zone: str, node: str) -> str:
    """
    Генерирует топик для статуса узла.
    
    Args:
        gh: UID теплицы (greenhouses.uid)
        zone: UID зоны (zones.uid)
        node: UID узла (nodes.uid)
    
    Returns:
        Топик в формате: hydro/{gh}/{zone}/{node}/status
    
    Example:
        >>> status("gh-1", "zn-1", "nd-ph-1")
        'hydro/gh-1/zn-1/nd-ph-1/status'
    """
    return f"hydro/{gh}/{zone}/{node}/status"


def heartbeat(gh: str, zone: str, node: str) -> str:
    """
    Генерирует топик для heartbeat узла.
    
    Args:
        gh: UID теплицы (greenhouses.uid)
        zone: UID зоны (zones.uid)
        node: UID узла (nodes.uid)
    
    Returns:
        Топик в формате: hydro/{gh}/{zone}/{node}/heartbeat
    
    Example:
        >>> heartbeat("gh-1", "zn-1", "nd-ph-1")
        'hydro/gh-1/zn-1/nd-ph-1/heartbeat'
    """
    return f"hydro/{gh}/{zone}/{node}/heartbeat"


def lwt(gh: str, zone: str, node: str) -> str:
    """
    Генерирует топик для LWT.

    Args:
        gh: UID теплицы (greenhouses.uid)
        zone: UID зоны (zones.uid)
        node: UID узла (nodes.uid)

    Returns:
        Топик в формате: hydro/{gh}/{zone}/{node}/lwt

    Example:
        >>> lwt("gh-1", "zn-1", "nd-ph-1")
        'hydro/gh-1/zn-1/nd-ph-1/lwt'
    """
    return f"hydro/{gh}/{zone}/{node}/lwt"


def config_report(gh: str, zone: str, node: str) -> str:
    """
    Генерирует топик для config_report.
    
    Args:
        gh: UID теплицы (greenhouses.uid)
        zone: UID зоны (zones.uid)
        node: UID узла (nodes.uid)
    
    Returns:
        Топик в формате: hydro/{gh}/{zone}/{node}/config_report
    
    Example:
        >>> config_report("gh-1", "zn-1", "nd-ph-1")
        'hydro/gh-1/zn-1/nd-ph-1/config_report'
    """
    return f"hydro/{gh}/{zone}/{node}/config_report"


def temp_command(node_uid_or_hw: str, ch: str) -> str:
    """
    Генерирует временный топик для команд (до привязки к зоне).
    
    Используется в режиме preconfig, когда узел еще не привязан к теплице и зоне.
    
    Args:
        node_uid_or_hw: UID узла или hardware_id
        ch: Имя канала (channels.key)
    
    Returns:
        Топик в формате: hydro/gh-temp/zn-temp/{node_uid_or_hw}/{ch}/command
    
    Example:
        >>> temp_command("esp32-ABCD1234", "pump_acid")
        'hydro/gh-temp/zn-temp/esp32-ABCD1234/pump_acid/command'
    """
    return f"hydro/gh-temp/zn-temp/{node_uid_or_hw}/{ch}/command"


def temp_error(node_uid_or_hw: str) -> str:
    """
    Генерирует временный топик для ошибок (до привязки к зоне).
    
    Используется в режиме preconfig, когда узел еще не привязан к теплице и зоне.
    
    Args:
        node_uid_or_hw: UID узла или hardware_id
    
    Returns:
        Топик в формате: hydro/gh-temp/zn-temp/{node_uid_or_hw}/error
    
    Example:
        >>> temp_error("esp32-ABCD1234")
        'hydro/gh-temp/zn-temp/esp32-ABCD1234/error'
    """
    return f"hydro/gh-temp/zn-temp/{node_uid_or_hw}/error"


def temp_status(node_uid_or_hw: str) -> str:
    """
    Генерирует временный топик для статуса (до привязки к зоне).
    
    Используется в режиме preconfig, когда узел еще не привязан к теплице и зоне.
    
    Args:
        node_uid_or_hw: UID узла или hardware_id
    
    Returns:
        Топик в формате: hydro/gh-temp/zn-temp/{node_uid_or_hw}/status
    
    Example:
        >>> temp_status("esp32-ABCD1234")
        'hydro/gh-temp/zn-temp/esp32-ABCD1234/status'
    """
    return f"hydro/gh-temp/zn-temp/{node_uid_or_hw}/status"


def temp_config_report(node_uid_or_hw: str) -> str:
    """
    Генерирует временный топик для config_report (до привязки к зоне).
    
    Args:
        node_uid_or_hw: UID узла или hardware_id
    
    Returns:
        Топик в формате: hydro/gh-temp/zn-temp/{node_uid_or_hw}/config_report
    """
    return f"hydro/gh-temp/zn-temp/{node_uid_or_hw}/config_report"


# Дополнительные функции для полноты (не указаны в требованиях, но могут быть полезны)

def temp_telemetry(node_uid_or_hw: str, ch: str) -> str:
    """
    Генерирует временный топик для телеметрии (до привязки к зоне).
    
    Args:
        node_uid_or_hw: UID узла или hardware_id
        ch: Имя канала (channels.key)
    
    Returns:
        Топик в формате: hydro/gh-temp/zn-temp/{node_uid_or_hw}/{ch}/telemetry
    """
    return f"hydro/gh-temp/zn-temp/{node_uid_or_hw}/{ch}/telemetry"


def temp_command_response(node_uid_or_hw: str, ch: str) -> str:
    """
    Генерирует временный топик для ответов на команды (до привязки к зоне).
    
    Args:
        node_uid_or_hw: UID узла или hardware_id
        ch: Имя канала (channels.key)
    
    Returns:
        Топик в формате: hydro/gh-temp/zn-temp/{node_uid_or_hw}/{ch}/command_response
    """
    return f"hydro/gh-temp/zn-temp/{node_uid_or_hw}/{ch}/command_response"


def temp_heartbeat(node_uid_or_hw: str) -> str:
    """
    Генерирует временный топик для heartbeat (до привязки к зоне).
    
    Args:
        node_uid_or_hw: UID узла или hardware_id
    
    Returns:
        Топик в формате: hydro/gh-temp/zn-temp/{node_uid_or_hw}/heartbeat
    """
    return f"hydro/gh-temp/zn-temp/{node_uid_or_hw}/heartbeat"


def temp_lwt(node_uid_or_hw: str) -> str:
    """
    Генерирует временный топик для LWT (до привязки к зоне).

    Args:
        node_uid_or_hw: UID узла или hardware_id

    Returns:
        Топик в формате: hydro/gh-temp/zn-temp/{node_uid_or_hw}/lwt
    """
    return f"hydro/gh-temp/zn-temp/{node_uid_or_hw}/lwt"
