"""
Единый источник истины для MQTT топиков.
Все функции генерации топиков должны быть здесь.
"""

from typing import Optional


def telemetry_topic(gh: str, zone: str, node: str, ch: str) -> str:
    """
    Генерирует топик для телеметрии.
    
    Args:
        gh: UID теплицы (greenhouses.uid)
        zone: UID зоны (zones.uid)
        node: UID узла (nodes.uid)
        ch: Имя канала (channels.key)
    
    Returns:
        Топик в формате: hydro/{gh}/{zone}/{node}/{ch}/telemetry
    """
    return f"hydro/{gh}/{zone}/{node}/{ch}/telemetry"


def command_topic(gh: str, zone: str, node: str, ch: str) -> str:
    """
    Генерирует топик для команд.
    
    Args:
        gh: UID теплицы
        zone: UID зоны
        node: UID узла
        ch: Имя канала
    
    Returns:
        Топик в формате: hydro/{gh}/{zone}/{node}/{ch}/command
    """
    return f"hydro/{gh}/{zone}/{node}/{ch}/command"


def command_response_topic(gh: str, zone: str, node: str, ch: str) -> str:
    """
    Генерирует топик для ответов на команды.
    
    Args:
        gh: UID теплицы
        zone: UID зоны
        node: UID узла
        ch: Имя канала
    
    Returns:
        Топик в формате: hydro/{gh}/{zone}/{node}/{ch}/command_response
    """
    return f"hydro/{gh}/{zone}/{node}/{ch}/command_response"


def error_topic(gh: str, zone: str, node: str) -> str:
    """
    Генерирует топик для ошибок узла.
    
    Args:
        gh: UID теплицы
        zone: UID зоны
        node: UID узла или hardware_id для temp-топиков
    
    Returns:
        Топик в формате: hydro/{gh}/{zone}/{node}/error
    """
    return f"hydro/{gh}/{zone}/{node}/error"


def temp_command_topic(identifier: str, ch: str) -> str:
    """
    Генерирует временный топик для команд (до привязки к зоне).
    
    Args:
        identifier: hardware_id или node_uid
        ch: Имя канала
    
    Returns:
        Топик в формате: hydro/gh-temp/zn-temp/{identifier}/{ch}/command
    """
    return f"hydro/gh-temp/zn-temp/{identifier}/{ch}/command"


def temp_error_topic(identifier: str) -> str:
    """
    Генерирует временный топик для ошибок (до привязки к зоне).
    
    Args:
        identifier: hardware_id или node_uid
    
    Returns:
        Топик в формате: hydro/gh-temp/zn-temp/{identifier}/error
    """
    return f"hydro/gh-temp/zn-temp/{identifier}/error"


def status_topic(gh: str, zone: str, node: str) -> str:
    """
    Генерирует топик для статуса узла.
    
    Args:
        gh: UID теплицы
        zone: UID зоны
        node: UID узла
    
    Returns:
        Топик в формате: hydro/{gh}/{zone}/{node}/status
    """
    return f"hydro/{gh}/{zone}/{node}/status"


def heartbeat_topic(gh: str, zone: str, node: str) -> str:
    """
    Генерирует топик для heartbeat узла.
    
    Args:
        gh: UID теплицы
        zone: UID зоны
        node: UID узла
    
    Returns:
        Топик в формате: hydro/{gh}/{zone}/{node}/heartbeat
    """
    return f"hydro/{gh}/{zone}/{node}/heartbeat"


def config_topic(gh: str, zone: str, node: str) -> str:
    """
    Генерирует топик для конфигурации узла.
    
    Args:
        gh: UID теплицы
        zone: UID зоны
        node: UID узла
    
    Returns:
        Топик в формате: hydro/{gh}/{zone}/{node}/config
    """
    return f"hydro/{gh}/{zone}/{node}/config"


def config_response_topic(gh: str, zone: str, node: str) -> str:
    """
    Генерирует топик для ответа на конфигурацию.
    
    Args:
        gh: UID теплицы
        zone: UID зоны
        node: UID узла
    
    Returns:
        Топик в формате: hydro/{gh}/{zone}/{node}/config_response
    """
    return f"hydro/{gh}/{zone}/{node}/config_response"

