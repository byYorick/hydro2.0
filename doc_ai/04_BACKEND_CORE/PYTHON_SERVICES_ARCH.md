# PYTHON_SERVICES_ARCH.md
# Архитектура Python-сервисов hydro2.0
# **ОБНОВЛЕНО ПОСЛЕ РЕФАКТОРИНГА 2025-12-25**

Документ описывает архитектуру Python-сервисов, их взаимодействие и структуру.

**КЛЮЧЕВЫЕ ИЗМЕНЕНИЯ:**
- ✅ Python сервисы используют Laravel API вместо прямых SQL
- ✅ Единый контракт через `/api/internal/effective-targets/batch`
- ✅ Убраны прямые запросы к `zone_recipe_instances` и `recipe_phases.targets`

**Связанные документы:**
- `../04_BACKEND_CORE/BACKEND_ARCH_FULL.md` — общая архитектура backend
- `../03_TRANSPORT_MQTT/MQTT_SPEC_FULL.md` — спецификация MQTT
- `../01_SYSTEM/DATAFLOW_FULL.md` — потоки данных


Compatible-With: Protocol 2.0, Backend >=3.0, Python >=3.0, Database >=3.0, Frontend >=3.0.
Breaking-change: legacy форматы/алиасы удалены, обратная совместимость не поддерживается.

---

## 1. Общая архитектура (обновлено)

Python-сервисы образуют промежуточный слой между:
- **Laravel API** (конфигурация, effective targets, пользователи)
- **MQTT Broker** (коммуникация с ESP32-нодами)
- **PostgreSQL** (хранение телеметрии и событий)

### Новые принципы после рефакторинга:
1. **Laravel API first** — все данные через REST API, не прямые SQL
2. **Effective targets контракт** — единый источник целей для контроллеров
3. **GrowCycle-centric** — логика строится вокруг активных циклов выращивания
4. **Stateless сервисы** — вся конфигурация из Laravel API
5. **Мониторинг** через Prometheus metrics

### Архитектурные изменения:
- ❌ **Убрано:** Прямые SQL запросы к recipe таблицам
- ✅ **Добавлено:** `LaravelApiRepository` для работы с API
- ✅ **Добавлено:** Batch endpoints для эффективного получения данных

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

## 3. Получение данных из Laravel (новая модель)

### 3.1. LaravelApiRepository

**Назначение:** Единый клиент для работы с Laravel API.

**Ключевые методы:**
- `get_effective_targets_batch(zone_ids)` — batch получение effective targets
- `get_effective_targets(zone_id)` — targets для одной зоны

**Пример использования:**
```python
from repositories.laravel_api_repository import LaravelApiRepository

repo = LaravelApiRepository()
targets = await repo.get_effective_targets_batch([1, 2, 3])

# Результат:
{
  "1": {
    "cycle_id": 123,
    "phase": {"name": "VEG", "started_at": "...", "due_at": "..."},
    "targets": {
      "ph": {"target": 6.0, "min": 5.8, "max": 6.2},
      "ec": {"target": 1.5, "min": 1.3, "max": 1.7},
      "irrigation": {"mode": "SUBSTRATE", "interval_sec": 3600}
    }
  }
}
```

### 3.2. RecipeRepository (обновлен)

**Изменения после рефакторинга:**
- ✅ Использует `LaravelApiRepository` вместо прямых SQL
- ✅ Получает данные через `/api/internal/effective-targets/batch`
- ❌ Убраны запросы к `zone_recipe_instances` и `recipe_phases.targets`

**Методы:**
- `get_zone_recipe_and_targets(zone_id)` — получает effective targets для зоны

---

## 4. Сервисы (обновлено после рефакторинга)

### 4.1. automation-engine (КЛЮЧЕВЫЕ ИЗМЕНЕНИЯ)

**Назначение:** Основной контроллер зон с новой логикой GrowCycle.

**Изменения после рефакторинга:**
- ✅ Получает effective targets через `LaravelApiRepository`
- ✅ Использует `recipe_revisions` вместо `recipe_phases.targets`
- ❌ Убраны прямые SQL запросы к recipe таблицам

**Ключевые компоненты:**
- `repositories/recipe_repository.py` — получение effective targets
- `repositories/laravel_api_repository.py` — клиент Laravel API
- `services/zone_controllers/` — контроллеры с новой логикой

**Функционал:**
- Получение effective targets для активных зон
- Управление pH/EC/irrigation/lighting/climate контроллерами
- Генерация команд на основе структурированных целей

---

### 4.2. scheduler (ОБНОВЛЕНО)

**Изменения:**
- ✅ Использует effective targets из Laravel API
- ✅ Расписания извлекаются из структурированных targets
- ✅ Контекст команды включает `cycle_id`

---

### 4.3. digital-twin (ОБНОВЛЕНО)

**Изменения:**
- ✅ Использует `recipe_revisions` и фазы по колонкам
- ✅ Симуляция работает с новой моделью ревизий

---

### 4.4. health-monitor (ОБНОВЛЕНО)

**Изменения:**
- ✅ Использует effective targets из Laravel API
- ✅ Мониторинг основан на новой доменной модели

---

### 4.5. mqtt-bridge (БЕЗ ИЗМЕНЕНИЙ)

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

**Порты:**
- **9300**: REST API для отправки команд
- **9301**: Prometheus metrics (`/metrics`)

**Функционал:**
- Подписка на топики `hydro/+/+/+/telemetry`
- Парсинг JSON payload
- Батчинг и upsert в `telemetry_samples`
- Обновление `telemetry_last`
- **REST API для централизованной публикации команд в MQTT**
- Обработка ошибок и реконнект

**REST API Endpoints:**
- `POST /commands` — универсальный endpoint для команд
- `POST /zones/{zone_id}/commands` — команды для конкретной зоны
- `POST /nodes/{node_uid}/commands` — команды для конкретной ноды
- `GET /health` — health check

**Зависимости:**
- MQTT Broker
- PostgreSQL

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
2. Накопление сообщений в батч
3. Периодическая запись батча в БД (upsert)
4. Обновление `telemetry_last` для последних значений

---

### 3.3. automation-engine

**Назначение:** Контроллер зон, проверка targets, публикация команд корректировки через history-logger.

**Порты:**
- **9401**: Prometheus metrics (`/metrics`)
- **9405**: REST API для приема задач от scheduler

**Функционал:**
- Периодическая загрузка конфигурации из Laravel
- Проверка активных зон с рецептами
- Сравнение текущих значений с targets (pH, EC)
- Публикация команд корректировки через history-logger REST API
- Прием и выполнение задач от scheduler
- Мониторинг через Prometheus

**REST API Endpoints (порт 9405):**
- `POST /scheduler/task` — прием задачи от scheduler
  - Body: `{"task_id": "...", "type": "...", "zone_id": ..., "params": {...}}`
  - Response: `{"status": "accepted", "task_id": "..."}`
- `POST /scheduler/bootstrap` — инициализация scheduler
- `POST /scheduler/bootstrap/heartbeat` — heartbeat от scheduler
- `GET /scheduler/task/{task_id}` — получение статуса задачи
- `POST /scheduler/internal/enqueue` — внутренний endpoint для постановки задач в очередь
- `GET /health` — health check

**Зависимости:**
- history-logger REST API (для публикации команд)
- PostgreSQL
- Laravel API

**Структура:**
```
automation-engine/
├── main.py          # Основной цикл проверки зон
├── test_main.py     # Тесты
├── requirements.txt
├── Dockerfile
└── README.md
```

**Алгоритм:**
1. Загрузка полной конфигурации из Laravel API
2. Получение активных зон с рецептами из БД
3. Для каждой зоны:
   - Получение текущих значений из `telemetry_last`
   - Сравнение с targets из рецепта
   - Публикация команд корректировки при отклонении
4. Повтор каждые 15 секунд

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

### 3.5. device-registry (LEGACY / NOT USED)

**Назначение:** Реестр устройств, хранение и выдача NodeConfig.

**Статус:** LEGACY / NOT USED — функционал полностью реализован в Laravel.

**Текущая реализация:**
- Функционал device-registry полностью реализован в Laravel:
  - Модели `DeviceNode` хранят информацию о нодах
  - Конфигурация нод хранится в БД через Laravel
  - NodeConfig может быть сгенерирован из данных БД
  - `NodeRegistryService` — регистрация нод
  - API `/api/nodes/register` — регистрация новых нод

**См. также:** `../../backend/services/device-registry/README.md` (описание legacy статуса)

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
- **ТОЛЬКО `history-logger`** публикует команды напрямую в MQTT: `hydro/{gh}/{zone}/{node}/{channel}/command`
- `automation-engine` → REST (9300) → `history-logger` → MQTT
- `scheduler` → REST (9405) → `automation-engine` → REST (9300) → `history-logger` → MQTT

**Архитектура потока команд:**
```
Scheduler → REST → Automation-Engine → REST → History-Logger → MQTT → Узлы
         (9405)                      (9300)
```

**Важно:** Централизованная публикация команд через history-logger обеспечивает единую точку логирования и мониторинга всех команд.

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

Согласно `../01_SYSTEM/01_PROJECT_STRUCTURE_PROD.md`, структура может быть реорганизована:

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

**Пример использования LARAVEL_API_TOKEN:**

```python
import os
import httpx
from common.env import get_settings

settings = get_settings()

# Запрос к Laravel API с токеном
headers = {}
if settings.laravel_api_token:
    headers['Authorization'] = f'Bearer {settings.laravel_api_token}'

response = httpx.get(
    f'{settings.laravel_api_url}/api/system/config/full',
    headers=headers,
    timeout=10.0
)
config = response.json()
```

**Генерация токена:**

Токен генерируется в Laravel через Laravel Sanctum:

```bash
# В Laravel контейнере
php artisan tinker
>>> $user = \App\Models\User::first();
>>> $token = $user->createToken('python-service')->plainTextToken;
>>> echo $token;
```

Полученный токен устанавливается в переменную окружения `LARAVEL_API_TOKEN` для Python сервисов.

### Прочее
- `TELEMETRY_BATCH_SIZE` — размер батча для телеметрии (по умолчанию: `200`)
- `TELEMETRY_FLUSH_MS` — интервал записи батча (по умолчанию: `500` мс)
- `COMMAND_TIMEOUT_SEC` — таймаут команды (по умолчанию: `30` сек)

---

## 7. Мониторинг

Все сервисы экспортируют Prometheus metrics:

- `mqtt-bridge`: порт 9000 (`/metrics`)
- `history-logger`: порт 9301 (`/metrics`)
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

- Документация проекта: `../`
- Backend архитектура: `../04_BACKEND_CORE/BACKEND_ARCH_FULL.md`
- MQTT спецификация: `../03_TRANSPORT_MQTT/MQTT_SPEC_FULL.md`
- Общий README: `../../backend/services/README.md`
