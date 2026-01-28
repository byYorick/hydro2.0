"""
Тесты для проверки безопасности SQL запросов.
Проверяет, что все запросы используют параметризацию и нет SQL injection уязвимостей.
"""
import pytest
import asyncio
from unittest.mock import patch, AsyncMock, MagicMock
import sys
import os

# Добавляем путь к модулям
sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, "/app")

try:
    from common.db import execute, fetch
except ImportError:
    # Для тестирования без полного контекста
    pass


@pytest.mark.asyncio
async def test_parameterized_queries():
    """Проверка, что запросы используют параметризацию."""
    with patch("common.db.get_pool") as mock_pool:
        mock_conn = AsyncMock()
        mock_conn.execute = AsyncMock(return_value="OK")
        mock_conn.fetch = AsyncMock(return_value=[])
        
        mock_pool_instance = MagicMock()
        mock_pool_instance.acquire.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_pool_instance.acquire.return_value.__aexit__ = AsyncMock(return_value=None)
        
        mock_pool.return_value = mock_pool_instance
        
        # Тест параметризованного запроса
        await execute("SELECT * FROM zones WHERE id = $1", 1)
        
        # Проверяем, что execute был вызван с параметрами
        mock_conn.execute.assert_called_once()
        call_args = mock_conn.execute.call_args
        assert call_args[0][0] == "SELECT * FROM zones WHERE id = $1"
        assert call_args[0][1] == 1  # Параметр передан отдельно


@pytest.mark.asyncio
async def test_sql_injection_protection():
    """Проверка защиты от SQL injection через параметризацию."""
    with patch("common.db.get_pool") as mock_pool:
        mock_conn = AsyncMock()
        mock_conn.execute = AsyncMock(return_value="OK")
        
        mock_pool_instance = MagicMock()
        mock_pool_instance.acquire.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_pool_instance.acquire.return_value.__aexit__ = AsyncMock(return_value=None)
        
        mock_pool.return_value = mock_pool_instance
        
        # Попытка SQL injection
        malicious_input = "1'; DROP TABLE zones; --"
        
        # Запрос должен обработать это безопасно через параметризацию
        await execute("SELECT * FROM zones WHERE id = $1", malicious_input)
        
        # Проверяем, что запрос содержит параметр, а не встроенную строку
        call_args = mock_conn.execute.call_args
        query = call_args[0][0]
        param = call_args[0][1]
        
        # Запрос не должен содержать встроенную строку
        assert malicious_input not in query
        # Параметр должен быть передан отдельно
        assert param == malicious_input


@pytest.mark.asyncio
async def test_handle_heartbeat_field_whitelist():
    """Проверка, что handle_heartbeat использует whitelist для полей."""
    # Импортируем только если модуль доступен
    try:
        history_logger_dir = os.path.join(os.path.dirname(__file__), "history-logger")
        if history_logger_dir not in sys.path:
            sys.path.insert(0, history_logger_dir)
        from mqtt_handlers import handle_heartbeat
        
        with patch("mqtt_handlers.execute") as mock_execute, \
             patch("mqtt_handlers._extract_node_uid") as mock_extract, \
             patch("mqtt_handlers._parse_json") as mock_parse:
            
            mock_extract.return_value = "test-node-uid"
            mock_parse.return_value = {
                "uptime": 12345,
                "free_heap": 50000,
                "rssi": -55
            }
            
            # Вызываем handle_heartbeat
            await handle_heartbeat("hydro/test/zn-1/test-node/heartbeat", b'{}')
            
            # Проверяем, что execute был вызван
            assert mock_execute.called
            
            # Проверяем, что запрос содержит только разрешенные поля
            call_args = mock_execute.call_args
            query = call_args[0][0]
            
            # Проверяем наличие разрешенных полей
            assert "uptime_seconds" in query or "last_heartbeat_at" in query
            # Проверяем, что используются параметры
            assert "$" in query
    except ImportError:
        pytest.skip("history_logger module not available")


@pytest.mark.asyncio
async def test_no_string_concatenation_in_sql():
    """Проверка, что нет конкатенации строк в SQL запросах."""
    import re
    
    # Ищем потенциально опасные паттерны в коде
    dangerous_patterns = [
        r'f".*SELECT.*\{',
        r'f".*INSERT.*\{',
        r'f".*UPDATE.*\{',
        r'f".*DELETE.*\{',
        r'%.*SELECT',
        r'\+.*SELECT',
    ]
    
    # Читаем файлы сервисов
    service_files = []
    for root, dirs, files in os.walk("."):
        if (
            "test" in root
            or "__pycache__" in root
            or ".venv" in root
            or "site-packages" in root
            or ".git" in root
            or "node_modules" in root
        ):
            continue
        for file in files:
            if file.endswith(".py"):
                filepath = os.path.join(root, file)
                if filepath.endswith("test_sql_security.py"):
                    continue
                try:
                    with open(filepath, 'r', encoding='utf-8') as f:
                        content = f.read()
                        for pattern in dangerous_patterns:
                            matches = re.findall(pattern, content)
                            if matches:
                                # Игнорируем безопасные случаи (комментарии, логирование)
                                safe_contexts = ['logger', 'print', '#', '"""', "'''"]
                                for match in matches:
                                    # Проверяем контекст
                                    match_index = content.find(match)
                                    context = content[max(0, match_index-50):match_index+50]
                                    if not any(safe in context for safe in safe_contexts):
                                        pytest.fail(
                                            f"Potentially dangerous SQL pattern found in {filepath}: {match}"
                                        )
                except Exception:
                    pass


@pytest.mark.asyncio
async def test_json_field_safety():
    """Проверка безопасности работы с JSON полями."""
    with patch("common.db.get_pool") as mock_pool:
        mock_conn = AsyncMock()
        mock_conn.execute = AsyncMock(return_value="OK")
        
        mock_pool_instance = MagicMock()
        mock_pool_instance.acquire.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_pool_instance.acquire.return_value.__aexit__ = AsyncMock(return_value=None)
        
        mock_pool.return_value = mock_pool_instance
        
        import json
        details = {"test": "value", "malicious": "'; DROP TABLE zones; --"}
        details_json = json.dumps(details)
        
        # JSON должен быть сериализован и передан как параметр
        await execute(
            "INSERT INTO zone_events (zone_id, type, details) VALUES ($1, $2, $3)",
            1, "TEST", details_json
        )
        
        call_args = mock_conn.execute.call_args
        query = call_args[0][0]
        params = call_args[0][1:]
        
        # Запрос не должен содержать встроенный JSON
        assert details_json not in query
        # JSON должен быть в параметрах
        assert params[2] == details_json


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
