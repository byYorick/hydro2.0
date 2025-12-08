# PYTHON_SERVICES_ARCH.md
# Архитектура Python-сервисов hydro2.0

Документ описывает архитектуру Python-сервисов, их взаимодействие и структуру.

**Связанные документы:**
- `doc_ai/04_BACKEND_CORE/BACKEND_ARCH_FULL.md` — общая архитектура backend
- `doc_ai/03_TRANSPORT_MQTT/MQTT_SPEC_FULL.md` — спецификация MQTT
- `doc_ai/01_SYSTEM/DATAFLOW_FULL.md` — потоки данных

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

**Назначение:** Подписка на MQTT, запись телеметрии в PostgreSQL.

**Функционал:**
- Подписка на топики `hydro/+/+/+/telemetry`
- Парсинг JSON payload
- Батчинг и upsert в `telemetry_samples`
- Обновление `telemetry_last`
- Обработка ошибок и реконнект
- **Batch processing оптимизации:**
  - Кеш `uid→id` с TTL refresh (60 секунд) для зон и нод
  - Batch resolve недостающих UID (один запрос вместо N)
  - Batch insert для `telemetry_samples`
  - Batch upsert для `telemetry_last` (один запрос для всех обновлений)
  - Backpressure при >90% заполнения очереди (sampling)
  - Метрики: `queue_size`, `dropped`, `overflow`

**Зависимости:**
- MQTT Broker
- PostgreSQL
- Redis (для очереди телеметрии)

**Структура:**
```
history-logger/
├── main.py          # Основной цикл подписки
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
   - Batch insert в `telemetry_samples`
   - Batch upsert в `telemetry_last`
4. Мониторинг размера очереди и backpressure

---

### 3.3. automation-engine

**Назначение:** Контроллер зон, проверка targets, публикация команд корректировки.

**Порт:** 9401 (Prometheus metrics)

**Функционал:**
- Периодическая загрузка конфигурации из Laravel
- Проверка активных зон с рецептами
- Сравнение текущих значений с targets (pH, EC)
- Публикация команд корректировки через MQTT
- Мониторинг через Prometheus
- **Адаптивная конкурентность:**
  - Автоматический расчет оптимального количества параллельных зон
  - Формула: `concurrency = (total_zones * avg_time) / target_cycle_time`
  - Диапазон: 5-50 параллельных зон
  - Метрики: `optimal_concurrency`, `zone_processing_time`, `zone_processing_errors`
- **Обработка ошибок:**
  - Явный учет ошибок по зонам в `process_zones_parallel()`
  - Метрики `zone_processing_errors` с детализацией по зонам
  - Алерты при >10% ошибок за цикл

**Зависимости:**
- MQTT Broker
- PostgreSQL
- Laravel API

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
   - Получение текущих значений из `telemetry_last`
   - Сравнение с targets из рецепта
   - Публикация команд корректировки при отклонении
   - Отслеживание ошибок и метрик
5. Повтор каждые 15 секунд

---

### 3.4. scheduler

**Назначение:** Расписания поливов/света из recipe phases, публикация команд на MQTT.

**Порт:** 9402 (Prometheus metrics)

**Функционал:**
- Загрузка активных расписаний из БД
- Парсинг time spec из recipe phases
- Публикация команд по расписанию
- Отслеживание выполненных команд

**Зависимости:**
- MQTT Broker
- PostgreSQL

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
4. Публикация команд при наступлении времени
5. Повтор каждые 60 секунд

---

### 3.5. device-registry (PLANNED)

**Назначение:** Реестр устройств, хранение и выдача NodeConfig.

**Статус:** PLANNED — функционал частично в Laravel.

**Планируемый функционал:**
- Хранение информации по нодам (ID, тип, конфиг каналов)
- Отдача конфига ноде при первом соединении/по запросу
- См. `backend/services/device-registry/README.md`

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
- `history-logger`: `hydro/+/+/+/telemetry`
- `automation-engine`: может подписываться на события (опционально)

**Публикации:**
- `mqtt-bridge`: `hydro/{gh}/{zone}/{node}/{channel}/command`
- `automation-engine`: команды корректировки
- `scheduler`: команды по расписанию

### 4.3. С PostgreSQL

**Направление:** Python → PostgreSQL

**Таблицы:**
- `telemetry_samples` — история телеметрии (запись через `history-logger`)
- `telemetry_last` — последние значения (обновление через `history-logger`)
- `zones`, `recipes`, `recipe_phases` — чтение через `automation-engine` и `scheduler`
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

Согласно `doc_ai/01_SYSTEM/01_PROJECT_STRUCTURE_PROD.md`, структура может быть реорганизована:

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
- Счетчики команд (отправлено, получено)
- Гистограммы задержек
- Счетчики ошибок

---

## 8. Тестирование

**Фреймворк:** pytest

**Структура:**
- `pytest.ini` — общая конфигурация
- `requirements-test.txt` — зависимости для тестов
- `test_main.py` в каждом сервисе — unit-тесты

**Запуск:**
```bash
pytest backend/services/
```

---

## 9. Деплой

**Docker Compose:**
- `backend/docker-compose.dev.yml` — для разработки
- `backend/docker-compose.prod.yml` — для продакшена

**Зависимости:**
- Все сервисы зависят от `mqtt` и `db`
- `automation-engine` зависит от `laravel`

**Health checks:**
- HTTP endpoints для проверки здоровья
- Prometheus metrics endpoints

---

## 10. Планы развития

1. **Реорганизация структуры** — переход на `src/` и `tests/` согласно документации
2. **Реализация device-registry** — отдельный Python-сервис
3. **Интеграционные тесты** — тесты в docker-compose стенде
4. **Улучшение мониторинга** — больше метрик, алерты
5. **Обработка ошибок** — retry логика, dead letter queue

---

## Ссылки

- Документация проекта: `doc_ai/`
- Backend архитектура: `doc_ai/04_BACKEND_CORE/BACKEND_ARCH_FULL.md`
- MQTT спецификация: `doc_ai/03_TRANSPORT_MQTT/MQTT_SPEC_FULL.md`
- Общий README: `backend/services/README.md`

