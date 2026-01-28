"""
Zone Prioritizer - приоритизация зон для обработки.
Критические зоны обрабатываются первыми.
"""
from typing import List, Dict, Any
import logging

logger = logging.getLogger(__name__)


def prioritize_zones(zones: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Приоритизация зон для обработки.
    
    Приоритеты:
    1. Низкий health_score (< 50) - критический приоритет
    2. Активные алерты - высокий приоритет
    3. Устаревшие данные телеметрии - средний приоритет
    4. Остальные зоны - обычный приоритет
    
    Args:
        zones: Список зон для приоритизации
    
    Returns:
        Отсортированный список зон по приоритету
    """
    def get_priority(zone: Dict[str, Any]) -> int:
        """Вычислить приоритет зоны."""
        priority = 0
        
        # Критические зоны (низкий health_score) - высший приоритет
        health_score = zone.get('health_score')
        if health_score is not None:
            if health_score < 50:
                priority += 1000  # Критический приоритет
            elif health_score < 80:
                priority += 500   # Высокий приоритет
        
        # Зоны с активными алертами
        active_alerts = zone.get('active_alerts_count', 0)
        if active_alerts > 0:
            priority += active_alerts * 100
        
        # Зоны с устаревшими данными телеметрии
        last_telemetry_age = zone.get('last_telemetry_age_minutes', 0)
        if last_telemetry_age > 30:
            priority += 50
        
        # Зоны с проблемами узлов
        node_status = zone.get('node_status', {})
        if node_status:
            total_nodes = node_status.get('total_count', 0)
            online_nodes = node_status.get('online_count', 0)
            if total_nodes > 0 and online_nodes < total_nodes:
                offline_ratio = (total_nodes - online_nodes) / total_nodes
                priority += int(offline_ratio * 100)
        
        return priority
    
    # Сортируем зоны по приоритету (убывание)
    sorted_zones = sorted(zones, key=get_priority, reverse=True)
    
    # Логируем приоритизацию
    if sorted_zones:
        top_priority = sorted_zones[0]
        logger.debug(
            f"Zone prioritization: {len(sorted_zones)} zones, "
            f"top priority: zone {top_priority.get('id')} (health: {top_priority.get('health_score')})"
        )
    
    return sorted_zones


