# LOGGING_AND_MONITORING.md
# Система логирования и мониторинга 2.0

Документ описывает, как система 2.0 должна собирать логи, метрики и алерты.

---

## 1. Цели

- видеть текущее состояние сервисов и узлов;
- быстро находить причины ошибок;
- получать уведомления о критических событиях;
- иметь историю для анализа и улучшений.

---

## 2. Компоненты Observability

1. **Логи приложений** (Python-сервис, Laravel).
2. **Метрики сервисов** (CPU, RAM, количество сообщений MQTT и т.п.).
3. **Метрики домена** (количество алертов, успешных команд и т.п.).
4. **Алертинг** (e-mail, Telegram).

---

## 3. Логи

Каждый сервис пишет структурированные логи (JSON):

```json
{
 "ts": "2025-11-15T10:00:00Z",
 "service": "python_scheduler",
 "level": "INFO",
 "zone_id": 2,
 "node_id": 11,
 "event": "COMMAND_SENT",
 "details": {
 "command_type": "dose",
 "channel": "pump_acid",
 "ml": 1.0
 }
}
```

Требования:

- уровни: DEBUG, INFO, WARNING, ERROR, CRITICAL;
- наличие минимальных полей: `ts`, `service`, `level`, `event`;
- отсутствие чувствительных данных в логах (пароли, токены).

---

## 4. Метрики

Сервисы публикуют метрики в систему мониторинга (Prometheus/иное):

- системные:
 - загрузка CPU;
 - использование памяти;
 - количество активных подключений к БД;
- доменные:
 - количество алертов по зонам;
 - количество команд в минуту;
 - количество сообщений MQTT в минуту.

Графики строятся в Grafana.

---

## 4.1. Мониторинг history-logger

### Статус сервиса

**Видимость статуса:**
- **Health endpoint**: `GET /health` — проверка доступности сервиса
- **Метрика**: `telemetry_queue_size` (Gauge) — текущий размер очереди Redis
- **Метрика**: `telemetry_queue_age_seconds` (Gauge) — возраст самого старого элемента в очереди

**Критические индикаторы:**
- Если `telemetry_queue_size > 10000` — очередь переполняется, требуется вмешательство
- Если `telemetry_queue_age_seconds > 300` — элементы задерживаются в очереди более 5 минут
- Если `telemetry_dropped_total > 0` — сообщения теряются

### Прогресс на уровне этапов

**Этапы обработки телеметрии:**
1. **Прием из MQTT** → `telemetry_received_total` (Counter)
2. **Добавление в очередь Redis** → `redis_operation_duration_seconds` (Histogram)
3. **Обработка батча** → `telemetry_processed_total` (Counter), `telemetry_batch_size` (Histogram)
4. **Запись в БД** → `telemetry_processing_duration_seconds` (Histogram), `database_errors_total` (Counter)

**Метрики прогресса:**
- `telemetry_received_total` — общее количество полученных сообщений
- `telemetry_processed_total` — общее количество обработанных сообщений
- Соотношение `telemetry_processed_total / telemetry_received_total` должно быть близко к 1.0
- `telemetry_batch_size` — размер батчей (целевое значение: 50-200 элементов)

### Выделенные представления мониторинга

**Grafana Dashboard: "History Logger Service"**

1. **Обзор сервиса:**
   - Статус сервиса (health check)
   - Размер очереди Redis (`telemetry_queue_size`)
   - Возраст элементов в очереди (`telemetry_queue_age_seconds`)
   - Скорость обработки (сообщений/сек)

2. **Поток телеметрии:**
   - График `telemetry_received_total` (rate)
   - График `telemetry_processed_total` (rate)
   - Разница между полученными и обработанными (показывает потери)
   - Размер батчей (`telemetry_batch_size`)

3. **Производительность:**
   - Время обработки батча (`telemetry_processing_duration_seconds`)
   - Время операций Redis (`redis_operation_duration_seconds`)
   - Время запросов к Laravel API (`laravel_api_request_duration_seconds`)

4. **Ошибки и потери:**
   - `telemetry_dropped_total` по причинам (validation_failed, queue_push_failed, missing_metric_type)
   - `database_errors_total` по типам ошибок
   - `node_hello_errors_total` по типам ошибок

5. **Регистрация узлов:**
   - `node_hello_received_total` — получено сообщений node_hello
   - `node_hello_registered_total` — успешно зарегистрировано узлов
   - `node_hello_errors_total` — ошибки регистрации

6. **Heartbeat:**
   - `heartbeat_received_total` по узлам — активность узлов

**Алерты:**
- `telemetry_queue_size > 10000` — очередь переполняется
- `telemetry_dropped_total{reason="queue_push_failed"} > 10` — критические потери данных
- `database_errors_total > 5` за 5 минут — проблемы с БД
- `telemetry_processing_duration_seconds > 5` — медленная обработка

---

## 4.2. Мониторинг automation-engine

### Статус сервиса

**Видимость статуса:**
- **Prometheus endpoint**: `http://service:9401/metrics` — все метрики сервиса
- **Метрика**: `zone_checks_total` (Counter) — общее количество проверок зон
- **Метрика**: `zone_check_seconds` (Histogram) — время проверки зон

**Критические индикаторы:**
- Если `automation_loop_errors_total > 0` — ошибки в основном цикле
- Если `config_fetch_errors_total > 0` — проблемы с получением конфигурации
- Если `mqtt_publish_errors_total > 0` — проблемы с публикацией команд

### Прогресс на уровне этапов

**Этапы обработки зоны:**
1. **Загрузка конфигурации** → `config_fetch_success_total` / `config_fetch_errors_total` (Counter)
2. **Получение данных зоны** → репозитории (логирование в коде)
3. **Проверка зоны** → `zone_checks_total` (Counter), `zone_check_seconds` (Histogram)
4. **Генерация команд** → `automation_commands_sent_total` (Counter) по зонам и метрикам
5. **Публикация команд** → `mqtt_publish_errors_total` (Counter) при ошибках

**Метрики прогресса:**
- `zone_checks_total` — количество проверенных зон
- `automation_commands_sent_total` — количество отправленных команд (по зонам и метрикам)
- `zone_check_seconds` — время обработки зоны (целевое: < 5 секунд)
- Соотношение успешных проверок к общему количеству зон

### Выделенные представления мониторинга

**Grafana Dashboard: "Automation Engine Service"**

1. **Обзор сервиса:**
   - Статус сервиса (доступность метрик)
   - Количество активных зон
   - Скорость обработки зон (зон/минуту)
   - Время последней успешной проверки

2. **Обработка зон:**
   - График `zone_checks_total` (rate) — частота проверок
   - График `zone_check_seconds` (p50, p95, p99) — время обработки
   - График `automation_commands_sent_total` по зонам — активность по зонам
   - График `automation_commands_sent_total` по метрикам — типы команд

3. **Конфигурация:**
   - `config_fetch_success_total` — успешные загрузки конфигурации
   - `config_fetch_errors_total` по типам ошибок — проблемы с конфигурацией
   - Время между загрузками конфигурации

4. **Команды и публикация:**
   - `automation_commands_sent_total` по зонам — распределение команд
   - `automation_commands_sent_total` по метрикам (pH, EC, irrigation, climate, light)
   - `mqtt_publish_errors_total` по типам ошибок — проблемы с MQTT

5. **Ошибки:**
   - `automation_loop_errors_total` по типам ошибок — ошибки в цикле
   - `error_handler_errors_total` по зонам (из error_handler.py) — общие ошибки обработки
   - График ошибок во времени

6. **Производительность:**
   - Время обработки зон (`zone_check_seconds`)
   - Параллелизм обработки (количество зон, обрабатываемых одновременно)
   - Задержка между циклами обработки

**Алерты:**
- `automation_loop_errors_total > 5` за 5 минут — критические ошибки в цикле
- `config_fetch_errors_total > 3` за 10 минут — проблемы с конфигурацией
- `mqtt_publish_errors_total > 10` за 5 минут — проблемы с публикацией команд
- `zone_check_seconds{p99} > 30` — медленная обработка зон
- Отсутствие `zone_checks_total` в течение 5 минут — сервис не обрабатывает зоны

**Дополнительные метрики для мониторинга:**
- Количество зон в статусе "требует корректировки"
- Количество зон с активными алертами
- Health score зон (если используется health_monitor.py)
- Стабильность pH/EC по зонам

---

## 5. Алертинг

Примеры алертов:

- недоступен брокер MQTT;
- Python-сервис не пишет телеметрию > N минут;
- количество ошибок команды OTA выше порога;
- слишком много алертов по одной зоне.

Алерты могут отправляться в:

- e-mail;
- Telegram-чат;
- панель UI.

---

## 6. Доступ к мониторингу для пользователей

### Быстрый доступ

**Grafana Dashboard:**
- **URL:** `http://localhost:3000` (или IP вашего сервера)
- **Логин (dev):** `admin` / **Пароль:** `admin`
- **Логин (prod):** `admin` / **Пароль:** из переменной `GRAFANA_ADMIN_PASSWORD`

**Prometheus UI:**
- **URL:** `http://localhost:9090`
- Прямой доступ к метрикам и алертам

**Доступные Dashboards:**
1. **History Logger Service** - мониторинг сервиса записи телеметрии
2. **Automation Engine Service** - мониторинг системы автоматизации зон
3. **System Overview** - общий обзор системы
4. **Alerts Dashboard** - активные алерты

### Подробное руководство

Полное руководство пользователя доступно в: `../08_SECURITY_AND_OPS/MONITORING_USER_GUIDE.md`

---

## 7. Правила для ИИ-агентов

1. Не удалять существующие логи и метрики без замены.
2. При добавлении новой важной логики — добавить логирование ключевых событий.
3. Не логировать секретные данные.

Наблюдаемость — это «глаза и уши» системы. Без неё любое сложное поведение превращается в «чёрный ящик».
