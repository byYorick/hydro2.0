# Интеграционные тесты для системы отправки ошибок

## Описание

Интеграционные тесты проверяют полный цикл обработки ошибок от нод:
1. Отправка ошибок через MQTT
2. Обработка в history-logger
3. Создание Alerts в Laravel
4. Обновление метрик в БД
5. Проверка метрик Prometheus

## Требования

- Docker и docker-compose
- Запущенные сервисы через `docker-compose.dev.yml`
- Python 3.8+
- Зависимости: `httpx`, `paho-mqtt`

## Установка зависимостей

```bash
cd backend/services
pip install httpx paho-mqtt
```

## Запуск тестов

### 1. Запустить сервисы

```bash
cd backend
docker-compose -f docker-compose.dev.yml up -d
```

Дождаться, пока все сервисы станут healthy:
```bash
docker-compose -f docker-compose.dev.yml ps
```

### 2. Запустить тесты

```bash
cd backend
python integration_tests/test_error_reporting.py
```

### 3. С переменными окружения

```bash
export MQTT_HOST=localhost
export MQTT_PORT=1883
export LARAVEL_URL=http://localhost:8080
export LARAVEL_API_TOKEN=dev-token-12345
export PROMETHEUS_URL=http://localhost:9090
export HISTORY_LOGGER_URL=http://localhost:9300

python integration_tests/test_error_reporting.py
```

## Что тестируется

### Test 1: Error Publishing
- Отправка ошибок через MQTT для всех типов нод
- Проверка успешной публикации

### Test 2: Error Processing
- Обработка ошибок в history-logger
- Проверка метрик Prometheus (`error_received_total`)

### Test 3: Alert Creation
- Создание Alerts в Laravel через API
- Проверка наличия тестовых Alerts

### Test 4: Error Metrics in DB
- Обновление счетчиков ошибок в БД
- Проверка полей `error_count`, `warning_count`, `critical_count`

### Test 5: Diagnostics Metrics
- Публикация diagnostics сообщений
- Проверка обработки метрик ошибок

## Ожидаемый результат

Все тесты должны пройти успешно:
```
✓ Test 1 passed: 6/6 errors published
✓ Test 2 passed: Found X error metrics in Prometheus
✓ Test 3 passed: Found X test alerts in Laravel
✓ Test 4 passed: Node has error metrics
✓ Test 5 passed: Diagnostics published
```

## Отладка

### Проверить MQTT сообщения

```bash
docker exec -it backend-mqtt-1 mosquitto_sub -h localhost -t "hydro/+/+/+/error" -v
```

### Проверить логи history-logger

```bash
docker logs backend-history-logger-1 -f
```

### Проверить метрики Prometheus

Открыть в браузере: http://localhost:9090

Запрос: `error_received_total`

### Проверить Alerts в Laravel

```bash
curl -H "Authorization: Bearer dev-token-12345" http://localhost:8080/api/alerts
```

## Примечания

- Тесты используют тестовые данные с префиксом `test-`
- После тестов можно очистить тестовые данные через Laravel API
- Для production тестов используйте соответствующие переменные окружения


