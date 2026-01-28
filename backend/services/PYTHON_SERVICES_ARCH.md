# PYTHON_SERVICES_ARCH.md
# Архитектура Python-сервисов hydro2.0

Документ описывает архитектуру Python-сервисов, их взаимодействие и структуру.

**Связанные документы:**
- `../../doc_ai/04_BACKEND_CORE/BACKEND_ARCH_FULL.md` — общая архитектура backend
- `../../doc_ai/03_TRANSPORT_MQTT/MQTT_SPEC_FULL.md` — спецификация MQTT
- `../../doc_ai/01_SYSTEM/DATAFLOW_FULL.md` — потоки данных

---

## 1. Общая архитектура

Python-сервисы образуют промежуточный слой между:
- **Laravel** (конфигурация, пользователи, API)
- **MQTT Broker** (коммуникация с ESP32-нодами)
- **PostgreSQL** (хранение телеметрии и событий)

### Принципы:
1. **Единая библиотека** (`common/`) для всех сервисов
2. **Асинхронная работа** с MQTT и БД
3. **Stateless сервисы** — вся конфигурация из Laravel/БД
4. **Мониторинг** через Prometheus metrics

---

## 2. Общая библиотека (`common/`)

### 2.1. Структура

```
common/
├── __init__.py
├── env.py          # Настройки из переменных окружения
├── db.py           # Подключение к PostgreSQL (asyncpg)
├── mqtt.py         # MQTT клиент (paho-mqtt)
├── schemas.py      # Pydantic схемы для валидации
├── commands.py     # Утилиты для работы с командами
└── test_db.py      # Тесты БД
```

### 2.2. Модули

#### `env.py` — Настройки
- Централизованное управление переменными окружения
- Dataclass `Settings` с дефолтными значениями
- Поддержка MQTT, PostgreSQL, Laravel API

#### `db.py` — База данных
- Connection pool к PostgreSQL (asyncpg)
- Функции `fetch()` и `execute()` для запросов
- Автоматическое управление пулом соединений

#### `mqtt.py` — MQTT клиент
- Класс `MqttClient` для подписки/публикации
- Автоматический реконнект
- Обработка сообщений через callbacks

#### `schemas.py` — Валидация данных
- Pydantic схемы для телеметрии
- Валидация команд
- Конвертация типов

#### `commands.py` — Работа с командами
- Утилиты для формирования команд
- Валидация параметров команд
- Форматирование для MQTT

---

## 3. Сервисы

### 3.1. mqtt-bridge

**Назначение:** FastAPI мост для отправки команд через MQTT.

**Порт:** 9000

**Функционал:**
- REST API для отправки команд на ноды
- Валидация команд через Pydantic
- Публикация команд в MQTT топики
- Логирование всех команд

**Эндпоинты:**
- `POST /bridge/zones/{zone_id}/commands` — отправка команды в зону
- `GET /metrics` — Prometheus metrics

**Зависимости:**
- MQTT Broker
- PostgreSQL (для логирования, опционально)

**Структура:**
```
mqtt-bridge/
├── main.py          # FastAPI приложение
├── publisher.py     # Публикация в MQTT
├── requirements.txt
├── Dockerfile
└── README.md
```

---

### 3.2. history-logger

**Назначение:** Подписка на MQTT, запись телеметрии в PostgreSQL, **единственная точка публикации команд в MQTT**.

**Функционал:**
- Подписка на топики `hydro/+/+/+/telemetry`
- Парсинг JSON payload
- Резолв/создание сенсоров в `sensors`
- Batch insert в `telemetry_samples` (по `sensor_id`)
- Batch upsert в `telemetry_last` (по `sensor_id`)
- Обработка ошибок и реконнект
- **Batch processing оптимизации:**
  - Кеш `uid→id` с TTL refresh (60 секунд) для зон и нод
  - Batch resolve недостающих UID (один запрос вместо N)
  - Batch insert для `telemetry_samples` (по `sensor_id`)
  - Batch upsert для `telemetry_last` (по `sensor_id`, один запрос для всех обновлений)
  - Backpressure при >95% заполнения очереди (sampling с коэффициентом 0.8-0.5)
  - Метрики и алерты:
    - `telemetry_queue_size` - текущий размер очереди
    - `telemetry_queue_dropped_total{reason}` - потерянные сообщения (overflow, backpressure)
    - `telemetry_queue_overflow_alerts_total` - количество отправленных алертов
    - `telemetry_dropped_total{reason}` - общие потери телеметрии
    - Автоматические алерты при >95% заполнения очереди (throttled 1 раз в минуту)

**Зависимости:**
- MQTT Broker
- PostgreSQL
- Redis (для очереди телеметрии)

**REST API Endpoints:**
- `POST /commands` - универсальный endpoint для публикации команд
- `POST /zones/{zone_id}/commands` - публикация команды для зоны
- `POST /nodes/{node_uid}/commands` - публикация команды для ноды
- `POST /ingest/telemetry` - прием телеметрии через HTTP
- `GET /health` - health check
- `GET /metrics` - Prometheus metrics

**Структура:**
```
history-logger/
├── main.py          # Основной цикл подписки + REST API
├── requirements.txt
├── Dockerfile
└── README.md
```

**Алгоритм:**
1. Подписка на MQTT топики телеметрии
2. Накопление сообщений в Redis очередь
3. Периодическая обработка батча из очереди:
   - Использование кеша для резолва zone_id/node_id
   - Batch resolve недостающих UID
   - Поиск/создание `sensor_id` в `sensors`
   - Batch insert в `telemetry_samples`
   - Batch upsert в `telemetry_last`
4. Мониторинг размера очереди и backpressure
5. **Прием команд через REST API:**
   - Валидация команд через Pydantic
   - Публикация команд в MQTT топики
   - Поддержка временных топиков для узлов без конфигурации

---

### 3.3. automation-engine

**Назначение:** Контроллер зон, проверка targets, публикация команд корректировки.

**Порты:** 
- 9401 (Prometheus metrics)
- 9405 (REST API для scheduler)

**Функционал:**
- Периодическая загрузка конфигурации из Laravel
- Проверка активных зон с рецептами
- Сравнение текущих значений с targets (pH, EC)
- Публикация команд корректировки через history-logger REST API
- REST API endpoint для scheduler (`/scheduler/command`)
- Мониторинг через Prometheus
- **Адаптивная конкурентность:**
  - Автоматический расчет оптимального количества параллельных зон
  - Формула: `concurrency = ceil((total_zones * avg_time) / target_cycle_time)`
  - Диапазон: 5-50 параллельных зон (защита от перегрузки)
  - Скользящее среднее времени обработки (последние 100 измерений)
  - Метрики:
    - `optimal_concurrency_zones` - рассчитанная оптимальная конкурентность
    - `zone_processing_time_seconds` - гистограмма времени обработки зон
    - `zone_processing_errors_total{zone_id, error_type}` - ошибки обработки с детализацией
- **Обработка ошибок:**
  - Явный учет ошибок по зонам в `process_zones_parallel()`
  - Детальная информация об ошибках: zone_id, zone_name, error_type, timestamp
  - Метрики `zone_processing_errors_total` с детализацией по зонам и типам ошибок
  - Алерты при >10% ошибок за цикл (warning при 10-30%, critical при >30%)
  - Интеграция с `error_handler` для централизованной обработки ошибок

**Зависимости:**
- PostgreSQL
- Laravel API
- History-Logger (REST API для публикации команд)

**Структура:**
```
automation-engine/
├── main.py          # Основной цикл проверки зон
├── config/
│   └── settings.py  # Настройки (ADAPTIVE_CONCURRENCY, TARGET_CYCLE_TIME_SEC)
├── test_main.py     # Тесты
├── requirements.txt
├── Dockerfile
└── README.md
```

**Алгоритм:**
1. Загрузка полной конфигурации из Laravel API
2. Получение активных зон с рецептами из БД
3. Расчет оптимальной конкурентности (если включена адаптивность)
4. Параллельная обработка зон с ограничением конкурентности:
   - Получение текущих значений из `telemetry_last` (join с `sensors`)
   - Сравнение с targets из рецепта
   - Публикация команд корректировки через history-logger REST API
   - Отслеживание ошибок и метрик
5. Повтор каждые 15 секунд

**REST API:**
- `POST /scheduler/command` - прием команд от scheduler
- `GET /health` - health check

---

### 3.4. scheduler

**Назначение:** Расписания поливов/света из recipe phases, публикация команд через automation-engine REST API.

**Порт:** 9402 (Prometheus metrics)

**Функционал:**
- Загрузка активных расписаний из БД
- Парсинг time spec из recipe phases
- Публикация команд через automation-engine REST API
- Отслеживание выполненных команд
- Мониторинг безопасности насосов (защита от сухого хода)

**Зависимости:**
- PostgreSQL
- Automation-Engine (REST API для публикации команд)

**Структура:**
```
scheduler/
├── main.py          # Основной цикл проверки расписаний
├── test_main.py     # Тесты
├── requirements.txt
├── Dockerfile
└── README.md
```

**Алгоритм:**
1. Загрузка активных расписаний из БД
2. Парсинг time spec (например, "08:00", "12:00,18:00")
3. Проверка текущего времени
4. Публикация команд через automation-engine REST API при наступлении времени
5. Мониторинг безопасности насосов (проверка потока после запуска)
6. Повтор каждые 60 секунд

**Команды:**
- Все команды отправляются через `send_command_via_automation_engine()` → automation-engine REST API
- Automation-engine проксирует команды в history-logger REST API
- History-logger публикует команды в MQTT

---

### 3.5. device-registry (PLANNED)

**Назначение:** Реестр устройств, хранение и выдача NodeConfig.

**Статус:** PLANNED — функционал частично в Laravel.

**Планируемый функционал:**
- Хранение информации по нодам (ID, тип, конфиг каналов)
- Отдача конфига ноде при первом соединении/по запросу
- См. `device-registry/README.md`

---

## 4. Взаимодействие между сервисами

### 4.1. С Laravel

**Направление:** Python → Laravel

**Метод:** HTTP REST API

**Использование:**
- `automation-engine` загружает конфигурацию через `/api/system/config/full`
- Все сервисы могут читать данные из PostgreSQL (общая БД)

**Аутентификация:**
- Token-based через `LARAVEL_API_TOKEN`

### 4.2. С MQTT Broker

**Направление:** Двустороннее

**Подписки:**
- `history-logger`: `hydro/+/+/+/telemetry`, `hydro/+/+/+/heartbeat`, `hydro/node_hello`, `hydro/+/+/+/node_hello`, `hydro/+/+/+/config_report`, `hydro/+/+/+/+/command_response`
- `automation-engine`: может подписываться на события (опционально)

**Публикации:**
- `history-logger`: **единственная точка публикации команд** → `hydro/{gh}/{zone}/{node}/{channel}/command`
- `mqtt-bridge`: `hydro/{gh}/{zone}/{node}/{channel}/command` (legacy, для внешних систем)

**Важно:** 
- `automation-engine` и `scheduler` **не публикуют команды напрямую в MQTT**
- Все команды проходят через `history-logger` REST API
- Это обеспечивает единую точку логирования и мониторинга команд

### 4.3. Между Python сервисами (REST API)

**Архитектура команд:**
```
Scheduler → REST (9405) → Automation-Engine → REST (9300) → History-Logger → MQTT → Ноды
```

**Endpoints:**
- **Automation-Engine** (`http://automation-engine:9405`):
  - `POST /scheduler/command` - прием команд от scheduler
  - `GET /health` - health check
  
- **History-Logger** (`http://history-logger:9300`):
  - `POST /commands` - универсальный endpoint для команд
  - `POST /zones/{zone_id}/commands` - команды для зоны
  - `POST /nodes/{node_uid}/commands` - команды для ноды
  - `POST /ingest/telemetry` - прием телеметрии через HTTP
  - `GET /health` - health check

**Аутентификация:**
- Bearer token через `Authorization: Bearer <token>`
- Токены: `HISTORY_LOGGER_API_TOKEN` или `PY_INGEST_TOKEN`

### 4.4. С PostgreSQL

**Направление:** Python → PostgreSQL

**Таблицы:**
- `sensors` — справочник сенсоров (type/label/scope, связь с zone/node)
- `telemetry_samples` — история телеметрии (запись через `history-logger`, `sensor_id`)
- `telemetry_last` — последние значения (обновление через `history-logger`, `sensor_id`)
- `zones`, `grow_cycles`, `effective_targets` — чтение через `automation-engine` и `scheduler` (через Laravel API)
- `commands` — логирование команд (опционально)

---

## 5. Структура проекта

### 5.1. Текущая структура (плоская)

```
backend/services/
├── common/              # Общая библиотека
│   ├── env.py
│   ├── db.py
│   ├── mqtt.py
│   ├── schemas.py
│   └── commands.py
├── mqtt-bridge/         # FastAPI мост REST→MQTT
│   ├── main.py          # Основной код
│   ├── publisher.py     # Публикация в MQTT
│   ├── requirements.txt
│   ├── Dockerfile
│   └── README.md
├── history-logger/      # Запись телеметрии
│   ├── main.py
│   ├── requirements.txt
│   ├── Dockerfile
│   └── README.md
├── automation-engine/    # Контроллер зон
│   ├── main.py
│   ├── test_main.py     # Тесты
│   ├── requirements.txt
│   ├── Dockerfile
│   └── README.md
├── scheduler/           # Расписания
│   ├── main.py
│   ├── test_main.py     # Тесты
│   ├── requirements.txt
│   ├── Dockerfile
│   └── README.md
├── device-registry/    # PLANNED
├── pytest.ini          # Конфигурация тестов
├── requirements-test.txt
└── README.md           # Общее описание
```

### 5.2. Планируемая структура (согласно документации)

Согласно `../../doc_ai/01_SYSTEM/01_PROJECT_STRUCTURE_PROD.md`, структура может быть реорганизована:

```
backend/services/
├── mqtt-bridge/
│   ├── src/            # Исходный код
│   │   ├── main.py
│   │   └── publisher.py
│   ├── tests/          # Тесты
│   ├── Dockerfile
│   └── README.md
```

**Примечание:** Текущая плоская структура работает и достаточна для MVP.  
Реорганизация с `src/` и `tests/` может быть выполнена в будущем для лучшей организации кода.

---

## 6. Переменные окружения

Общие для всех сервисов (через `common/env.py`):

### MQTT
- `MQTT_HOST` — хост MQTT брокера (по умолчанию: `mqtt`)
- `MQTT_PORT` — порт (по умолчанию: `1883`)
- `MQTT_USER`, `MQTT_PASS` — аутентификация (опционально)
- `MQTT_TLS` — использование TLS (по умолчанию: `0`)

### PostgreSQL
- `PG_HOST` — хост БД (по умолчанию: `db`)
- `PG_PORT` — порт (по умолчанию: `5432`)
- `PG_DB` — имя БД (по умолчанию: `hydro_dev`)
- `PG_USER` — пользователь (по умолчанию: `hydro`)
- `PG_PASS` — пароль (по умолчанию: `hydro`)

### Laravel API
- `LARAVEL_API_URL` — URL Laravel API (по умолчанию: `http://laravel`)
- `LARAVEL_API_TOKEN` — токен для аутентификации

### Прочее
- `TELEMETRY_BATCH_SIZE` — размер батча для телеметрии (по умолчанию: `200`)
- `TELEMETRY_FLUSH_MS` — интервал записи батча (по умолчанию: `500` мс)
- `COMMAND_TIMEOUT_SEC` — таймаут команды (по умолчанию: `30` сек)

---

## 7. Мониторинг

Все сервисы экспортируют Prometheus metrics:

- `mqtt-bridge`: порт 9000 (`/metrics`)
- `automation-engine`: порт 9401 (`/metrics`)
- `scheduler`: порт 9402 (`/metrics`)

**Метрики:**

**history-logger:**
- `telemetry_received_total` - получено сообщений из MQTT
- `telemetry_processed_total` - обработано сообщений
- `telemetry_dropped_total{reason}` - потерянные сообщения
- `telemetry_queue_size` - размер очереди Redis
- `telemetry_queue_dropped_total{reason}` - потерянные из-за переполнения очереди
- `telemetry_queue_overflow_alerts_total` - алерты о переполнении
- `telemetry_batch_size` - размер батчей
- `telemetry_processing_duration_seconds` - время обработки батча
- `telemetry_queue_age_seconds` - возраст самого старого элемента в очереди

**automation-engine:**
- `optimal_concurrency_zones` - оптимальная конкурентность
- `zone_processing_time_seconds` - время обработки зон
- `zone_processing_errors_total{zone_id, error_type}` - ошибки обработки
- `zone_checks_total` - количество проверок зон
- `check_latency_seconds` - задержка проверок
- `automation_commands_sent_total{zone_id, metric}` - отправлено команд
- `rest_command_errors_total{error_type}` - ошибки REST запросов к history-logger
- `command_rest_latency_seconds` - задержка REST запросов

**scheduler:**
- `schedule_executions_total{zone_id, task_type}` - выполненные расписания
- `active_schedules` - количество активных расписаний
- `scheduler_command_rest_errors_total{error_type}` - ошибки REST запросов к automation-engine

**history-logger:**
- `commands_received_total` - получено команд через REST API
- `commands_published_total{zone_id, metric}` - опубликовано команд в MQTT
- `command_publish_errors_total{error_type}` - ошибки публикации в MQTT
- `command_rest_requests_total` - количество REST запросов команд
- `command_rest_latency_seconds` - задержка обработки REST запросов

---

## 8. Тестирование

**Фреймворк:** pytest

**Структура:**
- `pytest.ini` — общая конфигурация
- `requirements-test.txt` — зависимости для тестов
- `test_main.py` в каждом сервисе — unit-тесты
- `tests/` — дополнительные тесты для специфичных функций

**Покрытие тестами:**

**history-logger:**
- `test_main.py` - основные тесты обработки телеметрии
- `test_commands.py` - тесты REST API endpoints для команд
- `test_batch_processing.py` - batch processing и кеширование
- `test_batch_upsert_optimization.py` - оптимизация batch upsert
- `test_overflow_metrics.py` - метрики overflow и алерты
- `test_metrics_and_improvements.py` - общие метрики
- `test_redis_queue_integration.py` - интеграция с Redis

**automation-engine:**
- `test_main.py` - основные тесты automation engine
- `test_command_bus.py` - тесты CommandBus с REST API
- `test_api.py` - тесты REST API endpoints
- `test_zone_automation_service.py` - сервис автоматизации зон
- `tests/test_adaptive_concurrency.py` - адаптивная конкурентность
- `tests/test_error_handling.py` - обработка ошибок
- `test_repositories.py` - репозитории
- `test_*_controller.py` - тесты контроллеров (pH/EC, climate, light, irrigation)

**Запуск:**
```bash
# Все тесты
pytest backend/services/

# Конкретный сервис
pytest backend/services/history-logger/
pytest backend/services/automation-engine/
pytest backend/services/scheduler/

# С покрытием
pytest --cov=backend/services/history-logger backend/services/history-logger/
```

**Покрытие тестами (после рефакторинга на REST API):**
- **Automation-Engine:** 20 тестов (CommandBus + REST API)
- **Scheduler:** 9 тестов (REST интеграция)
- **History-Logger:** 13 тестов (REST API endpoints)
- **Всего:** 42 теста, 100% успешность

---

## 9. Деплой

**Docker Compose:**
- `backend/docker-compose.dev.yml` — для разработки
- `backend/docker-compose.prod.yml` — для продакшена

**Зависимости:**
- Все сервисы зависят от `mqtt` и `db`
- `automation-engine` зависит от `laravel`

**Health checks:**
- HTTP endpoints для проверки здоровья (`/health`)
- Prometheus metrics endpoints (`/metrics`)
- Health checks в Docker Compose

**Порты:**
- `mqtt-bridge`: 9000 (REST API + metrics)
- `history-logger`: 9300 (REST API), 9301 (metrics)
- `automation-engine`: 9401 (metrics), 9405 (REST API)
- `scheduler`: 9402 (metrics)

---

## 10. Планы развития

1. **Реорганизация структуры** — переход на `src/` и `tests/` согласно документации
2. **Реализация device-registry** — отдельный Python-сервис
3. **Интеграционные тесты** — тесты в docker-compose стенде
4. **Улучшение мониторинга** — больше метрик, алерты
5. **Обработка ошибок** — retry логика, dead letter queue

---

## Ссылки

- Документация проекта: `../../doc_ai/`
- Backend архитектура: `../../doc_ai/04_BACKEND_CORE/BACKEND_ARCH_FULL.md`
- MQTT спецификация: `../../doc_ai/03_TRANSPORT_MQTT/MQTT_SPEC_FULL.md`
- Общий README: `README.md`
