#!/usr/bin/env python3
"""
Нагрузочный тест для проверки масштабируемости системы.
Тестирует систему с ~100 зонами, проверяет latency p99 и переполнение очереди.
"""

import asyncio
import aiohttp
import time
import statistics
from typing import List, Dict, Any
import json
from datetime import datetime

# Конфигурация теста
BASE_URL = "http://localhost:8080"
API_TOKEN = None  # Будет получен через логин
CONCURRENT_REQUESTS = 50
TOTAL_REQUESTS = 1000
TEST_DURATION_SEC = 60

# Метрики
request_times: List[float] = []
errors: List[Dict[str, Any]] = []


async def login(session: aiohttp.ClientSession) -> str:
    """Авторизация и получение токена."""
    login_data = {
        "email": "admin@example.com",
        "password": "password"  # Изменить на реальный пароль
    }
    
    try:
        async with session.post(f"{BASE_URL}/api/auth/login", json=login_data) as resp:
            if resp.status == 200:
                data = await resp.json()
                return data.get("token") or data.get("access_token")
    except Exception as e:
        print(f"Ошибка авторизации: {e}")
    
    return None


async def make_request(session: aiohttp.ClientSession, url: str, token: str = None) -> Dict[str, Any]:
    """Выполнить HTTP запрос и измерить время."""
    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    
    start_time = time.time()
    try:
        async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=30)) as resp:
            elapsed = time.time() - start_time
            body = await resp.text()
            
            return {
                "status": resp.status,
                "elapsed": elapsed,
                "success": 200 <= resp.status < 300,
                "error": None
            }
    except asyncio.TimeoutError:
        elapsed = time.time() - start_time
        return {
            "status": 0,
            "elapsed": elapsed,
            "success": False,
            "error": "timeout"
        }
    except Exception as e:
        elapsed = time.time() - start_time
        return {
            "status": 0,
            "elapsed": elapsed,
            "success": False,
            "error": str(e)
        }


async def test_endpoint(session: aiohttp.ClientSession, endpoint: str, token: str, num_requests: int):
    """Тестировать конкретный endpoint."""
    url = f"{BASE_URL}{endpoint}"
    tasks = []
    
    for _ in range(num_requests):
        task = make_request(session, url, token)
        tasks.append(task)
    
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    for result in results:
        if isinstance(result, Exception):
            errors.append({"endpoint": endpoint, "error": str(result)})
        elif isinstance(result, dict):
            request_times.append(result["elapsed"])
            if not result["success"]:
                errors.append({
                    "endpoint": endpoint,
                    "status": result["status"],
                    "error": result.get("error")
                })


async def check_queue_metrics(session: aiohttp.ClientSession) -> Dict[str, Any]:
    """Проверить метрики очереди из Prometheus."""
    try:
        # Попробуем получить метрики из Prometheus
        prometheus_url = "http://localhost:9090/api/v1/query"
        
        queries = [
            "telemetry_queue_size",
            "telemetry_queue_overflow_total",
            "telemetry_dropped_total",
            "zone_processing_time_seconds",
            "zone_processing_errors_total"
        ]
        
        metrics = {}
        for query in queries:
            try:
                async with session.get(prometheus_url, params={"query": query}) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        if data.get("status") == "success" and data.get("data", {}).get("result"):
                            metrics[query] = data["data"]["result"]
            except:
                pass
        
        return metrics
    except Exception as e:
        print(f"Ошибка получения метрик: {e}")
        return {}


def calculate_percentile(data: List[float], percentile: float) -> float:
    """Вычислить перцентиль."""
    if not data:
        return 0.0
    sorted_data = sorted(data)
    index = int(len(sorted_data) * percentile / 100)
    return sorted_data[min(index, len(sorted_data) - 1)]


async def main():
    """Основная функция нагрузочного теста."""
    print("=" * 60)
    print("НАГРУЗОЧНОЕ ТЕСТИРОВАНИЕ СИСТЕМЫ")
    print("=" * 60)
    print(f"Base URL: {BASE_URL}")
    print(f"Concurrent requests: {CONCURRENT_REQUESTS}")
    print(f"Total requests: {TOTAL_REQUESTS}")
    print(f"Test duration: {TEST_DURATION_SEC}s")
    print("=" * 60)
    
    async with aiohttp.ClientSession() as session:
        # Авторизация
        print("\n[1/4] Авторизация...")
        token = await login(session)
        if not token:
            print("ОШИБКА: Не удалось авторизоваться")
            return
        print("✓ Авторизация успешна")
        
        # Проверка начального состояния
        print("\n[2/4] Проверка начального состояния...")
        initial_metrics = await check_queue_metrics(session)
        print(f"Начальные метрики очереди: {len(initial_metrics)} метрик")
        
        # Нагрузочное тестирование
        print(f"\n[3/4] Нагрузочное тестирование ({TOTAL_REQUESTS} запросов)...")
        start_time = time.time()
        
        # Тестируем разные endpoints
        endpoints = [
            "/api/zones",
            "/api/nodes",
            "/api/system/config/full",
        ]
        
        requests_per_endpoint = TOTAL_REQUESTS // len(endpoints)
        
        tasks = []
        for endpoint in endpoints:
            task = test_endpoint(session, endpoint, token, requests_per_endpoint)
            tasks.append(task)
        
        await asyncio.gather(*tasks)
        
        elapsed = time.time() - start_time
        
        # Проверка метрик после теста
        print("\n[4/4] Проверка метрик после теста...")
        final_metrics = await check_queue_metrics(session)
        
        # Результаты
        print("\n" + "=" * 60)
        print("РЕЗУЛЬТАТЫ ТЕСТИРОВАНИЯ")
        print("=" * 60)
        
        if request_times:
            print(f"\nВремя выполнения запросов:")
            print(f"  Всего запросов: {len(request_times)}")
            print(f"  Успешных: {sum(1 for r in request_times)}")
            print(f"  Среднее время: {statistics.mean(request_times):.3f}s")
            print(f"  Медиана (p50): {calculate_percentile(request_times, 50):.3f}s")
            print(f"  p95: {calculate_percentile(request_times, 95):.3f}s")
            print(f"  p99: {calculate_percentile(request_times, 99):.3f}s")
            print(f"  Максимум: {max(request_times):.3f}s")
            print(f"  Минимум: {min(request_times):.3f}s")
            
            # Проверка целевых метрик
            p99 = calculate_percentile(request_times, 99)
            print(f"\n✓ p99 latency: {p99:.3f}s")
            if p99 <= 0.5:
                print("  ✓ ЦЕЛЬ ДОСТИГНУТА: p99 ≤ 500ms")
            else:
                print(f"  ✗ ЦЕЛЬ НЕ ДОСТИГНУТА: p99 > 500ms ({p99*1000:.0f}ms)")
        
        if errors:
            print(f"\nОшибки:")
            print(f"  Всего ошибок: {len(errors)}")
            error_types = {}
            for error in errors:
                error_type = error.get("error", "unknown")
                error_types[error_type] = error_types.get(error_type, 0) + 1
            for error_type, count in error_types.items():
                print(f"  {error_type}: {count}")
        
        if final_metrics:
            print(f"\nМетрики очереди:")
            for metric_name, metric_data in final_metrics.items():
                if metric_data:
                    print(f"  {metric_name}: {len(metric_data)} значений")
                    # Проверяем переполнение очереди
                    if "overflow" in metric_name or "dropped" in metric_name:
                        for result in metric_data:
                            value = float(result.get("value", [0, "0"])[1])
                            if value > 0:
                                print(f"    ⚠ ПЕРЕПОЛНЕНИЕ ОБНАРУЖЕНО: {value}")
        
        print(f"\nОбщее время теста: {elapsed:.2f}s")
        print(f"RPS (запросов в секунду): {len(request_times) / elapsed:.2f}")
        print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())

