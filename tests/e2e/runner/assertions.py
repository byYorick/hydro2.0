"""
Кастомные assertions для E2E тестов.
"""

import logging
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


class AssertionError(Exception):
    """Исключение для assertions."""
    pass


class Assertions:
    """Набор кастомных assertions."""
    
    @staticmethod
    def monotonic_command_status(commands: List[Dict[str, Any]]) -> bool:
        """
        Проверить, что статусы команд изменяются монотонно.
        
        Ожидаемая последовательность:
        QUEUED -> SENT -> ACCEPTED -> DONE
        
        Args:
            commands: Список команд с полем status, отсортированный по времени
            
        Returns:
            True если последовательность монотонна
            
        Raises:
            AssertionError: Если последовательность нарушена
        """
        status_order = {
            "QUEUED": 0,
            "SENT": 1,
            "ACCEPTED": 2,
            "DONE": 3,
            "FAILED": -1,
            "TIMEOUT": -1,
            "SEND_FAILED": -1
        }
        
        last_status_value = -1
        
        for cmd in commands:
            status = cmd.get("status", "").upper()
            status_value = status_order.get(status, -1)
            
            if status_value == -1:
                # FAILED, TIMEOUT, SEND_FAILED - это финальные статусы
                continue
            
            if status_value < last_status_value:
                raise AssertionError(
                    f"Command status sequence violation: "
                    f"expected status >= {last_status_value}, got {status_value} ({status})"
                )
            
            last_status_value = status_value
        
        return True
    
    @staticmethod
    def alert_dedup_count(alerts: List[Dict[str, Any]], max_duplicates: int = 1) -> bool:
        """
        Проверить, что количество дубликатов алертов не превышает максимум.
        
        Args:
            alerts: Список алертов
            max_duplicates: Максимальное количество дубликатов одного алерта
            
        Returns:
            True если дубликатов не больше максимума
            
        Raises:
            AssertionError: Если дубликатов больше максимума
        """
        # Группируем алерты по ключевым полям (например, type, message, node_id)
        alert_groups: Dict[str, List[Dict[str, Any]]] = {}
        
        for alert in alerts:
            # Создаем ключ для группировки
            key = f"{alert.get('type')}_{alert.get('message')}_{alert.get('node_id')}"
            if key not in alert_groups:
                alert_groups[key] = []
            alert_groups[key].append(alert)
        
        # Проверяем количество дубликатов
        for key, group in alert_groups.items():
            if len(group) > max_duplicates + 1:  # +1 потому что первый не дубликат
                raise AssertionError(
                    f"Too many duplicate alerts for key '{key}': "
                    f"found {len(group)}, max allowed {max_duplicates + 1}"
                )
        
        return True
    
    @staticmethod
    def unassigned_present(
        nodes: List[Dict[str, Any]],
        expected_count: Optional[int] = None
    ) -> bool:
        """
        Проверить наличие непривязанных узлов.
        
        Args:
            nodes: Список узлов
            expected_count: Ожидаемое количество непривязанных узлов (None для любого > 0)
            
        Returns:
            True если условие выполнено
            
        Raises:
            AssertionError: Если условие не выполнено
        """
        unassigned = [n for n in nodes if not n.get("zone_id") or n.get("zone_id") is None]
        count = len(unassigned)
        
        if expected_count is None:
            if count == 0:
                raise AssertionError("Expected at least one unassigned node, but found none")
        else:
            if count != expected_count:
                raise AssertionError(
                    f"Expected {expected_count} unassigned nodes, but found {count}"
                )
        
        return True
    
    @staticmethod
    def attached(
        nodes: List[Dict[str, Any]],
        expected_count: Optional[int] = None
    ) -> bool:
        """
        Проверить наличие привязанных узлов.
        
        Args:
            nodes: Список узлов
            expected_count: Ожидаемое количество привязанных узлов (None для любого > 0)
            
        Returns:
            True если условие выполнено
            
        Raises:
            AssertionError: Если условие не выполнено
        """
        attached = [n for n in nodes if n.get("zone_id") is not None]
        count = len(attached)
        
        if expected_count is None:
            if count == 0:
                raise AssertionError("Expected at least one attached node, but found none")
        else:
            if count != expected_count:
                raise AssertionError(
                    f"Expected {expected_count} attached nodes, but found {count}"
                )
        
        return True
    
    @staticmethod
    def equals(actual: Any, expected: Any, message: Optional[str] = None) -> bool:
        """
        Проверить равенство значений.
        
        Args:
            actual: Фактическое значение
            expected: Ожидаемое значение
            message: Сообщение об ошибке
            
        Returns:
            True если значения равны
            
        Raises:
            AssertionError: Если значения не равны
        """
        if actual != expected:
            msg = message or f"Expected {expected}, but got {actual}"
            raise AssertionError(msg)
        return True
    
    @staticmethod
    def contains(container: Any, item: Any, message: Optional[str] = None) -> bool:
        """
        Проверить, что контейнер содержит элемент.
        
        Args:
            container: Контейнер (список, строка, словарь)
            item: Элемент для поиска
            message: Сообщение об ошибке
            
        Returns:
            True если элемент найден
            
        Raises:
            AssertionError: Если элемент не найден
        """
        if item not in container:
            msg = message or f"Expected {item} to be in {container}"
            raise AssertionError(msg)
        return True

