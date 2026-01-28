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
- PostgreSQL БД с созданными тестовыми данными (создаются автоматически)

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

### 2. Создать тестовые данные (опционально)

Тестовые данные создаются автоматически при первом запуске тестов, но можно создать вручную:

```bash
cd backend
docker exec backend-laravel-1 php artisan tinker --execute="
\$gh = \App\Models\Greenhouse::firstOrCreate(['uid' => 'gh-test-1'], ['name' => 'Test Greenhouse', 'type' => 'indoor', 'timezone' => 'UTC', 'provisioning_token' => 'test-token-12345']);
\$zone = \App\Models\Zone::firstOrCreate(['uid' => 'zn-test-1'], ['greenhouse_id' => \$gh->id, 'name' => 'Test Zone', 'status' => 'online']);
// ... создание нод
"
```

### 3. Запустить тесты

```bash
cd backend
python3 integration_tests/test_error_reporting.py
```

### 4. С переменными окружения

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
- Создание Alerts в БД через `error_handler`
- Проверка наличия тестовых Alerts в БД
- Alerts создаются напрямую в PostgreSQL (не через API)

### Test 4: Error Metrics in DB
- Обновление счетчиков ошибок в БД
- Проверка полей `error_count`, `warning_count`, `critical_count` в таблице `nodes`
- Проверка выполняется через прямой доступ к БД

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

### Проверить Alerts в БД

```bash
docker exec backend-laravel-1 php artisan tinker --execute="
\$alerts = \App\Models\Alert::where('type', 'node_error')->orderBy('created_at', 'desc')->limit(10)->get(['id', 'code', 'type', 'status', 'created_at']);
foreach (\$alerts as \$alert) {
    echo \$alert->code . ' - ' . \$alert->status . PHP_EOL;
}
"
```

### Проверить метрики ошибок в нодах

```bash
docker exec backend-laravel-1 php artisan tinker --execute="
\$nodes = \App\Models\DeviceNode::whereIn('uid', ['nd-ph-test-1', 'nd-ec-test-1'])->get(['uid', 'error_count', 'warning_count', 'critical_count']);
foreach (\$nodes as \$node) {
    echo \$node->uid . ': error=' . \$node->error_count . ', warning=' . \$node->warning_count . ', critical=' . \$node->critical_count . PHP_EOL;
}
"
```

## Примечания

- Тесты используют тестовые данные с префиксом `test-` (gh-test-1, zn-test-1, nd-*-test-1)
- Тестовые данные создаются автоматически при первом запуске
- После тестов можно очистить тестовые данные через Laravel tinker или API
- Для production тестов используйте соответствующие переменные окружения
- Тесты проверяют alerts и метрики напрямую в БД (не через API), чтобы избежать проблем с аутентификацией

## Результаты

Все 5 тестов должны пройти успешно:
- ✅ Error Publishing: 6/6 ошибок опубликовано
- ✅ Error Processing: метрики найдены в history-logger и Prometheus
- ✅ Alert Creation: alerts созданы в БД
- ✅ Error Metrics in DB: метрики обновлены во всех нодах
- ✅ Diagnostics Metrics: diagnostics сообщения опубликованы


