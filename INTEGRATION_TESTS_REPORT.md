# Отчет по интеграционным тестам системы отправки ошибок

## Дата: 2025-01-28

## Статус: ✅ ГОТОВО К ЗАПУСКУ

Созданы интеграционные тесты для проверки полного цикла обработки ошибок от нод.

## Созданные файлы

### 1. `backend/integration_tests/test_error_reporting.py`
Основной скрипт интеграционных тестов, который проверяет:

- **Test 1: Error Publishing** - Отправка ошибок через MQTT для всех типов нод
- **Test 2: Error Processing** - Обработка ошибок в history-logger и проверка метрик Prometheus
- **Test 3: Alert Creation** - Создание Alerts в Laravel через API
- **Test 4: Error Metrics in DB** - Обновление счетчиков ошибок в БД
- **Test 5: Diagnostics Metrics** - Публикация и обработка diagnostics сообщений

### 2. `backend/integration_tests/README.md`
Документация по запуску и использованию тестов.

### 3. `backend/integration_tests/run_tests.sh`
Скрипт для удобного запуска тестов с проверкой доступности сервисов.

### 4. Обновлен `backend/docker-compose.dev.yml`
Добавлен сервис `integration-tests` для запуска тестов в Docker окружении.

## Как запустить тесты

### Вариант 1: Через Docker Compose (рекомендуется)

```bash
cd backend
docker-compose -f docker-compose.dev.yml --profile tests run --rm integration-tests
```

### Вариант 2: Через скрипт

```bash
cd backend
./integration_tests/run_tests.sh
```

### Вариант 3: Напрямую (если установлены зависимости)

```bash
cd backend
export MQTT_HOST=localhost
export MQTT_PORT=1883
export LARAVEL_URL=http://localhost:8080
export LARAVEL_API_TOKEN=dev-token-12345
export PROMETHEUS_URL=http://localhost:9090
export HISTORY_LOGGER_URL=http://localhost:9300

python3 integration_tests/test_error_reporting.py
```

## Требования

1. **Запущенные сервисы:**
   - MQTT брокер (порт 1883)
   - Laravel API (порт 8080)
   - History Logger (порт 9300)
   - Prometheus (порт 9090)

2. **Зависимости Python:**
   - `httpx` - для HTTP запросов
   - `paho-mqtt` - для MQTT публикации

## Что тестируется

### 1. Отправка ошибок через MQTT
- Публикация ошибок для всех 6 типов нод (ph, ec, pump, climate, relay, light)
- Разные уровни ошибок (ERROR, WARNING, CRITICAL)
- Разные компоненты (сенсоры, драйверы, MQTT)

### 2. Обработка ошибок
- Проверка подписки history-logger на топик `hydro/+/+/+/error`
- Проверка метрик Prometheus `error_received_total`

### 3. Создание Alerts
- Проверка создания Alerts через Laravel API
- Проверка наличия тестовых Alerts в БД

### 4. Обновление метрик в БД
- Проверка полей `error_count`, `warning_count`, `critical_count` в таблице `nodes`
- Проверка обновления метрик через Laravel API

### 5. Diagnostics метрики
- Публикация diagnostics сообщений
- Проверка обработки метрик ошибок в diagnostics

## Ожидаемый результат

При успешном прохождении всех тестов:

```
=== Integration Tests Summary ===
Passed: 5/5
✓ error_publishing: {'test': 'error_publishing', 'passed': True, 'published': 6, 'total': 6}
✓ error_processing: {'test': 'error_processing', 'passed': True, 'metrics_count': X}
✓ alert_creation: {'test': 'alert_creation', 'passed': True, 'alerts_count': X}
✓ error_metrics_in_db: {'test': 'error_metrics_in_db', 'passed': True, ...}
✓ diagnostics_metrics: {'test': 'diagnostics_metrics', 'passed': True, ...}
```

## Отладка

### Проверить MQTT сообщения

```bash
docker exec -it backend-mqtt-1 mosquitto_sub -h localhost -t "hydro/+/+/+/error" -v
```

### Проверить логи history-logger

```bash
docker logs backend-history-logger-1 -f | grep -i error
```

### Проверить метрики Prometheus

Открыть в браузере: http://localhost:9090

Запрос: `error_received_total`

### Проверить Alerts в Laravel

```bash
curl -H "Authorization: Bearer dev-token-12345" http://localhost:8080/api/alerts | jq
```

## Примечания

- Тесты используют тестовые данные с префиксом `test-` (gh-test-1, zn-test-1, nd-*-test-1)
- После тестов можно очистить тестовые данные через Laravel API
- Для production тестов используйте соответствующие переменные окружения и токены

## Следующие шаги

1. ✅ Запустить тесты на реальном окружении
2. ✅ Проверить обработку ошибок в production
3. ✅ Настроить автоматический запуск тестов в CI/CD
4. ✅ Добавить тесты для edge cases (массовые ошибки, таймауты, и т.д.)


