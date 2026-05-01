# Automation Engine

Система автоматизации управления параметрами теплиц с поддержкой параллельной обработки зон, централизованной обработкой ошибок и модульной архитектурой.

## Актуальный AE3 runtime (2026-03-24)

- Canonical runtime API:
  - `ae3lite/runtime/app.py` (entrypoint FastAPI)
  - `ae3lite/api/compat_endpoints.py` (bind `POST /zones/{id}/start-cycle`)
  - `ae3lite/api/internal_endpoints.py` (canonical internal task/status API)
  - `ae3lite/application/use_cases/get_zone_automation_state.py` (zone state read-path)
- Legacy runtime package удалён из рабочего кода; canonical implementation живёт только в `ae3lite/*`.
- Single-writer policy:
  - lease уникален на зону (`start_cycle:{zone_id}`);
  - при активной lease повторный запуск зоны блокируется;
  - runtime работает fail-closed без fallback writer-режима.

## История изменений

Детальные отчёты о промежуточных этапах декомпозиции и старых refactor-step
перенесены в архивные материалы `doc_ai/00_ARCHIVE/REPORTS/*`.
Этот README оставляет только текущее состояние канонического runtime AE3-Lite.

## 🏗️ Архитектура

### Слоистая архитектура (AE3-Lite)

```
┌─────────────────────────────────────┐
│  main.py → ae3lite.main → serve()   │
│  FastAPI + worker (см. ae3lite/)    │
└──────────────┬──────────────────────┘
               │
┌──────────────▼──────────────────────┐
│  ae3lite/runtime (app, worker)      │
│  use cases, handlers, workflow      │
└──────────────┬──────────────────────┘
               │
    ┌──────────┴──────────┐
    │                     │
┌───▼────────────┐   ┌────▼─────────────────┐
│ Read models /  │   │ HL client, metrics   │
│ repositories   │   │ intent / task repos  │
└───┬────────────┘   └──────────────────────┘
```

### Основные компоненты

#### 1. **AE3-Lite** (`ae3lite/`)
- Канонический runtime: задачи, workflow, коррекция, полив, совместимые HTTP-эндпоинты.

#### 2. **Repositories** (`repositories/`, общие read-path)
- `ZoneRepository`, `TelemetryRepository`, `NodeRepository`, `RecipeRepository` — SQL-доступ, используется утилитами и тестами; `RecipeRepository.get_zone_data_batch` агрегирует снимок зоны.

#### 3. **Общие модули** (корень пакета)
- `recipe_utils.py`, `health_monitor.py`, `alerts_manager.py`, `command_bus.py` и др. — вспомогательная логика и интеграции.

#### 4. **Infrastructure**
- `infrastructure/command_bus.py` — публикация команд через history-logger REST API (вспомогательные сценарии)
- `error_handler.py`, `exceptions.py` (корень пакета) — обработка ошибок
- `utils/retry.py` — retry для критических операций
- Состояние workflow AE3 — репозитории и read-model в `ae3lite/infrastructure/`

#### 5. **Configuration** (`config/`)
- `settings.py` - централизованные настройки (пороги, интервалы, множители)

### Scheduler Task API (planner contract)

`automation-engine` принимает от `scheduler` абстрактные задачи расписания:

- `POST /zones/{zone_id}/start-cycle` -> каноничный wake-up для запуска цикла
- `GET /zones/{zone_id}/state` -> текущий state workflow автоматики зоны для UI-панели
- `GET /zones/{zone_id}/control-mode` -> активный режим (`auto|semi|manual`) и разрешенные manual-step
- `POST /zones/{zone_id}/control-mode` -> переключение режима
- `POST /zones/{zone_id}/manual-step` -> запуск ручного шага (только в `semi|manual`)
- `GET /health/live` -> liveness probe
- `GET /health/ready` -> readiness probe (`CommandBus + DB`)

Поддерживаемые `task_type`:
- `irrigation`
- `lighting`
- `ventilation`
- `solution_change`
- `mist`
- `diagnostics`

Важно: scheduler не должен отправлять device-level команды напрямую.  
Детализация и исполнение задач выполняются внутри `automation-engine` через `CommandBus`.

Дополнительно:
- `idempotency_key` в `POST /zones/{zone_id}/start-cycle` обязателен;
- повторный вызов с тем же `idempotency_key` возвращает deduplicated `accepted` без двойного исполнения.

Маппинг `task_type -> node_types/cmd/params` вынесен в `config/scheduler_task_mapping.py` и поддерживает override из `payload.config.execution`.
Снимки статусов scheduler-task (`accepted/running/completed/failed`) сохраняются в `scheduler_logs` для восстановления после рестарта.

## 🚀 Возможности

### Основной функционал
- ✅ Исполнение workflow и коррекций в рамках AE3-Lite (задачи зон, fail-closed guards)
- ✅ Batch-запросы к БД там, где это даёт read-model / `get_zone_data_batch`
- ✅ Интеграция с history-logger для команд; алерты через Laravel ingest (`common/alert_publisher`)
- ✅ Health / recipe утилиты в корне сервиса при необходимости внешних сценариев

### Надежность
- ✅ Централизованная обработка ошибок
- ✅ Retry механизм для критических операций
- ✅ Валидация входных данных
- ✅ Кастомные исключения с контекстом
- ✅ Структурированное логирование

### Производительность
- ✅ Параллельная обработка зон (ускорение в 3-5 раз)
- ✅ Batch запросы к БД (снижение нагрузки на 40-50%)
- ✅ Оптимизированные SQL запросы с CTE

## 📦 Установка

```bash
# Установка зависимостей
pip install -r requirements.txt

# Запуск
python main.py
```

## ⚙️ Конфигурация

Настройки находятся в `config/settings.py`:

```python
from config.settings import get_settings

settings = get_settings()
print(settings.MAIN_LOOP_SLEEP_SECONDS)  # 15
print(settings.MAX_CONCURRENT_ZONES)     # 5
print(settings.PH_CORRECTION_THRESHOLD)  # 0.2
```

### Основные настройки

- `MAIN_LOOP_SLEEP_SECONDS` - интервал между циклами обработки (по умолчанию: 15)
- `MAX_CONCURRENT_ZONES` - максимальное количество параллельно обрабатываемых зон (по умолчанию: 5)
- `PH_CORRECTION_THRESHOLD` - минимальная разница для корректировки pH (по умолчанию: 0.2)
- `EC_CORRECTION_THRESHOLD` - минимальная разница для корректировки EC (по умолчанию: 0.2)
- `PH_DOSING_MULTIPLIER` - множитель для расчета дозировки pH (по умолчанию: 10.0)
- `EC_DOSING_MULTIPLIER` - множитель для расчета дозировки EC (по умолчанию: 100.0)

## 🧪 Тестирование

```bash
# Из корня репозитория (рекомендуется)
make test-ae

# Внутри контейнера automation-engine (рабочая директория /app)
pytest -q
pytest -q test_ae3lite_execute_task.py
```

### Покрытие тестами

- Основной объём — **`test_ae3lite_*.py`** и контрактные тесты read-model.
- Репозитории и `recipe_utils` покрыты unit-тестами с моками `fetch` / `execute`.

## 📊 Метрики Prometheus

Метрики доступны через встроенный ASGI endpoint `http://localhost:9405/metrics/`:

- `automation_loop_errors_total` - ошибки в главном цикле
- `config_fetch_errors_total` - ошибки получения конфигурации
- `config_fetch_success_total` - успешные получения конфигурации
- `zone_checks_total` - количество проверок зон
- `zone_check_seconds` - длительность проверки зоны
- `automation_commands_sent_total{zone_id, metric}` - отправленные команды
- `rest_command_errors_total{error_type}` - ошибки REST запросов к history-logger
- `command_rest_latency_seconds` - задержка REST запросов
- `automation_errors_total` - общие ошибки автоматизации

## 🔧 Использование

### Запуск сервиса (production / dev)

Точка входа процесса — **`python main.py`** (делегирует в `ae3lite.main`).  
HTTP API и worker поднимаются из `ae3lite.runtime.serve` (см. `ae3lite/runtime/app.py`).

### Программный доступ к read-model

```python
from repositories import RecipeRepository

repo = RecipeRepository()
snapshot = await repo.get_zone_data_batch(zone_id=1)
# snapshot["recipe_info"], ["telemetry"], ["nodes"], ["capabilities"]
```

Логика циклов, коррекции и команд — внутри **`ae3lite/`** (handlers, use cases, gateways).

## 📁 Структура проекта

```
automation-engine/
├── main.py                 # Точка входа → ae3lite
├── ae3lite/                # Канонический runtime (API, worker, handlers, use cases)
├── config/                 # Настройки процесса
├── repositories/         # SQL read-path (зоны, телеметрия, узлы, рецепты)
├── services/             # Зарезервировано (пакет может быть пустым)
├── infrastructure/       # CommandBus и сопутствующие модули (если есть)
├── utils/
├── recipe_utils.py
├── health_monitor.py
├── alerts_manager.py
├── command_bus.py
├── correction_cooldown.py
├── test_*.py
└── tests/                  # Доп. pytest-модули
```

## 📝 Примечание

Для архитектурных инвариантов и runtime-контрактов используйте:
- `backend/services/automation-engine/AGENT.md`
- `doc_ai/04_BACKEND_CORE/ae3lite.md`
