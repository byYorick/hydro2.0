# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Язык общения

**ВАЖНО: Всегда общайся на русском языке (русский язык) при взаимодействии с пользователем.**

Это русскоязычный проект. Все общение, объяснения, сообщения коммитов и обновления документации должны быть на русском языке, за исключением:
- Кода (который следует английским конвенциям для переменных, функций и т.д.)
- Технических терминов, которые обычно используются на английском (например, "MQTT", "REST API", "docker compose")
- Существующей документации на английском в `doc_ai/` (которая использует русский язык с английскими техническими терминами)

## Обзор проекта

Это монорепозиторий для системы управления гидропонной теплицей (hydro2.0), содержащий:
- **Прошивки ESP32** для различных сенсорных/исполнительных узлов (pH, EC, климат, насосы, освещение, реле)
- **Laravel backend** (API Gateway) с Inertia.js + Vue 3 фронтендом
- **Python микросервисы** (MQTT bridge, history logger, automation engine); расписания полива/света — **в Laravel**
- **PostgreSQL + TimescaleDB** для телеметрии и временных рядов
- **MQTT протокол** для связи узлов ↔ backend
- **Android мобильное приложение**
- **Инфраструктура** (Docker, Kubernetes, стек мониторинга)

**Ключевая архитектурная концепция:** Иерархия Теплица → Зоны → Узлы → Каналы. Система использует управление на основе зон, где каждая зона может иметь несколько узлов, а узлы имеют каналы для сенсоров/исполнительных устройств.

## Основная документация

**ВСЕГДА читай это в первую очередь при работе над задачей:**
- `doc_ai/INDEX.md` — главный индекс документации (source of truth)
- `doc_ai/SYSTEM_ARCH_FULL.md` — архитектура системы
- `doc_ai/ARCHITECTURE_FLOWS.md` — **архитектурные схемы и пайплайны** (визуализация потоков данных)
- `doc_ai/DEV_CONVENTIONS.md` — конвенции разработки
- `README.md` — быстрые ссылки и обзор структуры

**Примечание:** `doc_ai/` — это единственный source of truth для документации. Папка `docs/` удалена; все её уникальные материалы перенесены в `doc_ai/13_TESTING/`, `doc_ai/12_ANDROID_APP/` и `doc_ai/07_FRONTEND/ui_refs/`.

### Документация по компонентам

- **Backend:** `doc_ai/04_BACKEND_CORE/BACKEND_ARCH_FULL.md`, `backend/README.md`
- **Python сервисы:** `doc_ai/04_BACKEND_CORE/PYTHON_SERVICES_ARCH.md`, `backend/services/README.md`
- **AE3 (automation-engine):** `doc_ai/04_BACKEND_CORE/ae3lite.md`, `AE3_RUNTIME_EVENT_CONTRACT.md`, `AE3_IRR_FAILSAFE_AND_ESTOP_CONTRACT.md`, `AE3_IRR_LEVEL_SWITCH_EVENT_CONTRACT.md`, `AUTOMATION_CONFIG_AUTHORITY.md`
- **history-logger API:** `doc_ai/04_BACKEND_CORE/HISTORY_LOGGER_API.md` — REST API спецификация
- **Прошивки:** `doc_ai/02_HARDWARE_FIRMWARE/`, `firmware/README.md`
- **MQTT протокол:** `doc_ai/03_TRANSPORT_MQTT/MQTT_SPEC_FULL.md`
- **NodeConfig:** `firmware/NODE_CONFIG_SPEC.md`
- **Frontend:** `doc_ai/07_FRONTEND/FRONTEND_ARCH_FULL.md`
- **Android:** `doc_ai/12_ANDROID_APP/`
- **Зоны/Рецепты:** `doc_ai/06_DOMAIN_ZONES_RECIPES/`
- **Effective Targets:** `doc_ai/06_DOMAIN_ZONES_RECIPES/EFFECTIVE_TARGETS_SPEC.md` — спецификация контроллеров

## Основные команды разработки

### Сборка и запуск

```bash
# Запустить dev окружение (из корня проекта)
make up
# Или: docker compose -f backend/docker-compose.dev.yml up -d --build

# Остановить dev окружение
make down

# Операции с базой данных
make migrate      # Выполнить миграции
make seed         # Заполнить базу тестовыми данными
make reset-db     # Полная пересборка + заполнение
```

### Тестирование

```bash
# Запустить все тесты (PHP + Python через mqtt-bridge)
make test

# Запустить тесты протокольных контрактов
make protocol-check

# Laravel — все тесты
docker compose -f backend/docker-compose.dev.yml exec laravel php artisan test

# Laravel — один тест / фильтр
docker compose -f backend/docker-compose.dev.yml exec laravel php artisan test --filter=TestClassName
docker compose -f backend/docker-compose.dev.yml exec laravel php artisan test tests/Unit/FooTest.php

# Python — automation-engine (рекомендуемый способ для AE тестов)
docker compose -f backend/docker-compose.dev.yml exec automation-engine pytest -x -q
docker compose -f backend/docker-compose.dev.yml exec automation-engine pytest tests/path/to/test_file.py -x -q
docker compose -f backend/docker-compose.dev.yml exec automation-engine pytest -x -q -k "test_name"

# Python — history-logger
docker compose -f backend/docker-compose.dev.yml exec history-logger pytest -x -q

# Python — mqtt-bridge / общие схемы
docker compose -f backend/docker-compose.dev.yml exec mqtt-bridge pytest -x -q

# Frontend тесты (из backend/laravel/)
npm run test              # Vitest unit тесты
npm run test:ui           # Vitest с UI
npm run e2e               # Playwright E2E тесты
npm run e2e:ci            # E2E тесты для CI
```

### Качество кода

```bash
# PHP линтинг (Pint)
make lint

# Frontend линтинг (из backend/laravel/)
npm run lint
npm run typecheck
```

### Другие инструменты

```bash
# Smoke тесты
make smoke

# Аудит горячих точек
make audit

# Генерация ERD диаграммы
make erd
```

### Просмотр логов

```bash
make logs-ae        # automation-engine
make logs-hl        # history-logger
make logs-mqttb     # mqtt-bridge
make logs-laravel   # laravel
make logs-core      # laravel + ae + hl + mqtt-bridge (все основные)
make logs SERVICE=<имя>  # произвольный сервис
```

### Доступ к dev сервисам

| Сервис | REST API | Метрики |
|--------|----------|---------|
| Laravel | http://localhost:8080 | — |
| mqtt-bridge | http://localhost:9000 | — |
| history-logger | http://localhost:9300 | http://localhost:9301/metrics |
| automation-engine | http://localhost:9405 | http://localhost:9401/metrics |
| Laravel (метрики scheduler-dispatch) | http://localhost:8080 | http://localhost:8080/api/system/scheduler/metrics |
| Grafana | http://localhost:3000 | — |
| Prometheus | http://localhost:9090 | — |

## Архитектурные особенности

### Архитектура Backend

**Laravel (API Gateway):**
- Технологический стек: Laravel 12 + Inertia.js + Vue 3 + TypeScript
- Обрабатывает REST API, WebSocket (Reverb), аутентификацию (Sanctum)
- Frontend использует Pinia для управления состоянием, ECharts для визуализаций
- Расположен в: `backend/laravel/`

**Python микросервисы** (расположены в `backend/services/`):
- `mqtt-bridge` — FastAPI мост для REST→MQTT (порт 9000)
- `history-logger` — подписчик MQTT, пишет телеметрию в PostgreSQL, **единственная точка публикации команд в MQTT** (порт 9300)
- `automation-engine` — контроллер зон, проверяет targets, отправляет команды через history-logger REST API (порт 9405).
  **Канонический runtime — `ae3lite/`** (AE2/`ae2lite` удалён). См. `doc_ai/04_BACKEND_CORE/ae3lite.md`, `AE3_RUNTIME_EVENT_CONTRACT.md`, `AE3_IRR_FAILSAFE_AND_ESTOP_CONTRACT.md`.
- расписания полива/освещения из фаз рецептов планирует **Laravel** (`automation:dispatch-schedules`, intents в БД, wake-up через `POST /zones/{id}/start-cycle`)

**Архитектура потока команд:**
```
Laravel scheduler-dispatch → REST → Automation-Engine → REST → History-Logger → MQTT → Узлы
```

**Критично:** Только `history-logger` публикует команды напрямую в MQTT. Остальные сервисы используют REST API для обеспечения централизованного логирования и мониторинга.

### Архитектура прошивок

- **Язык:** C с фреймворком ESP-IDF
- **Расположение:** `firmware/`
- **Структура:**
  - `common/components/` — общие компоненты (MQTT, WiFi, I2C, OLED, сенсоры, драйверы)
  - `nodes/` — проекты прошивок для конкретных узлов (pump_node, ph_node, ec_node, climate_node, light_node, relay_node)

**Ключевые компоненты:**
- `node_framework` — унифицированный фреймворк для всех узлов (обработка конфига, команд, телеметрии, Safe Mode)
- `mqtt_manager` — MQTT клиент и маршрутизатор топиков
- `config_storage` — сохранение NodeConfig
- Драйверы сенсоров: `trema_ph`, `trema_ec`, `sht3x` (темп/влажность), `ina209` (ток), `ccs811` (CO2)
- Драйверы исполнительных устройств: `pump_driver`, `relay_driver`, `pwm_driver`, `ws2811_driver`

**Система NodeConfig:**
- Узлы получают конфигурацию через MQTT
- Конфигурация хранится в NVS (Non-Volatile Storage)
- Спецификация: `firmware/NODE_CONFIG_SPEC.md`

### MQTT протокол

- **Брокер:** Eclipse Mosquitto (порт 1883)
- **Структура топиков:** Иерархическая с greenhouse_uid/node_uid
- **Типы сообщений:** telemetry, commands, config, heartbeat
- **Полная спецификация:** `doc_ai/03_TRANSPORT_MQTT/MQTT_SPEC_FULL.md`

### Хранение данных

- **PostgreSQL + TimescaleDB** для телеметрии временных рядов
- **Политики хранения:**
  - Сырые данные: 7-30 дней (настраивается)
  - Агрегированные (1m, 1h, daily): до 12 месяцев
- **Автоматическая агрегация:** Laravel команды `telemetry:cleanup-raw` и `telemetry:aggregate`

### Стек мониторинга

- **Prometheus** (порт 9090) — сбор метрик
- **Grafana** (порт 3000) — дашборды визуализации
- **Alertmanager** (порт 9093) — управление алертами
- Конфигурация: `configs/dev/prometheus.yml`, `configs/dev/alertmanager/`

## Конвенции разработки

### Git Workflow

**Ветки:**
- `main` — стабильная, развертываемая версия
- `feature/<описание-задачи>` — ветки фич

**Формат коммитов:**
```
<тип>: <описание>

Типы: feat, fix, refactor, docs, test, chore
Примеры:
  feat: добавлен mqtt телеметрия энкодер для ph ноды
  fix: исправлена инициализация i2c шины для ec ноды
  docs: расширены шаблоны задач для ai агентов
```

### Стандарты кодирования

**Прошивки (C/ESP-IDF):**
- Файлы: `snake_case.c`, `snake_case.h`
- Функции/переменные: `snake_case`
- Типы/enum: `PascalCase` (например, `PhNodeState`, `MeasurementResult`)
- Макросы/константы: `UPPER_SNAKE_CASE`
- Всегда обрабатывай коды ошибок ESP-IDF
- Используй ESP_LOG с соответствующими тегами и уровнями

**Backend (PHP/Laravel):**
- Следуй конвенциям Laravel (стандарты PSR)
- Используй Pint для форматирования кода: `make lint`
- Четкое разделение слоев: транспорт → бизнес-логика → доступ к данным

**Frontend (Vue 3 + TypeScript):**
- TypeScript strict mode включен
- Используй composition API
- Компонентные тесты с Vitest + Vue Test Utils
- E2E тесты с Playwright
- Запускай `npm run lint` и `npm run typecheck` перед коммитом

**Python сервисы:**
- Следуй конвенциям PEP 8
- Требуются type hints
- Pytest для тестирования
- Расположены в `backend/services/`

### Подход "Документация в первую очередь"

Из `DEV_CONVENTIONS.md`:
1. **Сначала документация** — обнови/создай спецификацию (Markdown)
2. **Определи интерфейс** — заголовки, API контракты, MQTT схемы
3. **Реализуй** — напиши фактический код

### Политика Breaking Changes

**Защищенные границы (НЕТ breaking changes без миграции):**
- ESP32 → MQTT → Python → PostgreSQL → Laravel → Vue пайплайн
- MQTT топики/полезная нагрузка, форматы команд, схемы базы данных
- Обязательные ID, API ответы, Inertia props

**Остальные области:** Breaking changes разрешены без обратной совместимости (проект в активной разработке).

## Правила совместимости и архитектурные ограничения

### Приоритет правил (от общего к частному)

1. Корневой `AGENTS.md` / `CLAUDE.md`
2. Спецификации слоя в `doc_ai/0X_.../*`
3. Локальный `AGENTS.md` в подкаталоге задачи
4. Гайды ИИ в `doc_ai/10_AI_DEV_GUIDES/`

Локальные правила могут **уточнять** базовые, но не **противоречить** спецификациям слоя. При конфликте или сомнении — следовать более строгому требованию и запросить уточнение у пользователя.

### Обязательный минимум перед работой

- Проверить наличие локального `AGENTS.md` в подкаталоге задачи (может содержать специфичные правила для компонента).
- Открыть 2-3 ключевых документа своего слоя из `doc_ai/`.
- Backend / Python-сервисы / БД / e2e — команды выполнять **внутри Docker-контейнеров** проекта (ESP-IDF прошивки собираются вне Docker).

**Docker-compose файлы проекта:**
- `backend/docker-compose.dev.yml` — основной dev (Linux/macOS)
- `backend/docker-compose.dev.win.yml` — dev для Windows
- `backend/docker-compose.ci.yml` — CI окружение
- `backend/docker-compose.prod.yml` — production
- `tests/e2e/docker-compose.e2e.yml` — e2e сценарии workflow/automation
- `tests/node_sim/Dockerfile` — симулятор узлов
- `infra/hil/docker-compose.hil.yml` — Hardware-in-the-Loop

### Источники истины

- **`doc_ai/`** — единственный source of truth, всегда редактируй здесь (включая `13_TESTING/` для E2E-документации)
- **Локальные `AGENTS.md`** — всегда проверяй их наличие в подкаталогах перед работой

### Чек-лист при изменении протоколов/данных

При изменении MQTT протокола, схемы БД или API **ОБЯЗАТЕЛЬНО**:

1. Обновить MQTT спецификации:
   - `doc_ai/03_TRANSPORT_MQTT/MQTT_NAMESPACE.md`
   - `doc_ai/03_TRANSPORT_MQTT/MQTT_SPEC_FULL.md`
   - `doc_ai/03_TRANSPORT_MQTT/BACKEND_NODE_CONTRACT_FULL.md`

2. При новых `message_type` или `channel`:
   - Обновить `doc_ai/02_HARDWARE_FIRMWARE/NODE_CHANNELS_REFERENCE.md`
   - Обновить обработчики в Python сервисах

3. Обновить `doc_ai/05_DATA_AND_STORAGE/DATA_MODEL_REFERENCE.md`

4. При изменении API/Inertia props — обновить соответствующий фронтенд

5. Если затронут путь публикации команд — обновить `doc_ai/04_BACKEND_CORE/HISTORY_LOGGER_API.md`

6. Если затронуты циклы коррекции pH/EC — обновить `doc_ai/06_DOMAIN_ZONES_RECIPES/CORRECTION_CYCLE_SPEC.md` и `EFFECTIVE_TARGETS_SPEC.md`

7. Если добавлена телеметрия — обеспечить запись в `telemetry_samples` и `telemetry_last`

8. Добавить в commit/PR строку совместимости:
   ```
   Compatible-With: Protocol 2.0, Backend >=3.0, Python >=3.0, Database >=3.0, Frontend >=3.0
   ```

### Зоны ответственности компонентов

| Компонент | ✅ Разрешено | ❌ Запрещено |
|-----------|-------------|-------------|
| **Laravel** | Добавлять маршруты, модели, миграции, страницы | Менять Inertia формат без обновления Vue; обращаться к MQTT напрямую |
| **Python services** | Алгоритмы контроллеров, обработка MQTT | Менять форматы команд; обходить централизованное логирование |
| **PostgreSQL** | Добавлять таблицы/поля через миграции | Ручной DDL; удалять обязательные поля; циклические FK |
| **MQTT** | Добавлять новые `message_type` | Менять существующие топики/форматы; нарушать иерархию |
| **Frontend (Vue)** | Улучшать UI/UX, добавлять компоненты | Ломать структуру props; игнорировать типы TypeScript |

### Критичные технические запреты

1. **ESP32 прошивки:**
   - НЕ использовать динамическое выделение памяти в горячих путях (критично для стабильности)

2. **Backend / Laravel:**
   - Laravel НЕ обращается к MQTT напрямую — только через Python-сервисы
   - Все изменения БД ТОЛЬКО через Laravel-миграции (не ручной DDL)
   - НЕ менять `auth/roles` без явной необходимости (см. `doc_ai/10_AI_DEV_GUIDES/BACKEND_LARAVEL_PG_AI_GUIDE.md`)
   - Новые публичные API документировать **до или вместе** с кодом

3. **PostgreSQL:**
   - Все изменения через Laravel-миграции; ручной DDL запрещён (см. `doc_ai/10_AI_DEV_GUIDES/DATABASE_SCHEMA_AI_GUIDE.md`)
   - Новые сущности/поля сначала описывать в `doc_ai/05_DATA_AND_STORAGE/DATA_MODEL_REFERENCE.md`, затем миграция
   - НЕ менять типы полей телеметрии без согласования всех слоёв пайплайна
   - Избегать циклических FK-зависимостей
   - Не удалять обязательные поля без миграции данных

4. **MQTT:**
   - Формат топиков СТРОГО: `hydro/{gh}/{zone}/{node}/{channel}/{message_type}`
   - НЕ менять существующие форматы сообщений без обновления ВСЕГО пайплайна
   - Новые `message_type` / `channel` только при одновременном обновлении `NODE_CHANNELS_REFERENCE.md`, `DATA_MODEL_REFERENCE.md` и обработчиков Python

5. **Команды к узлам:**
   - Отправка ТОЛЬКО через history-logger → MQTT (не обходить штатный dispatch и HL)
   - Запрещено публиковать команды в MQTT напрямую из Laravel или automation-engine в обход history-logger

6. **Телеметрия:**
   - При добавлении новых метрик — обязательная запись в `telemetry_samples` **и** `telemetry_last` (см. `doc_ai/05_DATA_AND_STORAGE`)

### Поведение ИИ-агента

- Следовать `doc_ai/10_AI_DEV_GUIDES/AI_ASSISTANT_DEV_GUIDE.md` как базовому чек-листу
- **Не придумывать архитектуру заново** и не игнорировать спецификации `doc_ai/`
- Если изменение затрагивает пайплайн `ESP32 → MQTT → Python → PG → Laravel → Vue` или схемы взаимодействия и выглядит **несовместимым или неочевидным** — **остановиться и запросить подтверждение** у пользователя
- Если данных недостаточно — требовать список вопросов, а не домысливать
- Для сложных задач — сначала предоставить план и список затронутых файлов, потом реализация
- Всегда отвечать на русском языке; английские термины — только как технические идентификаторы (API, протоколы, имена функций)

### Работа с ИИ-агентами

Для постановки задач ИИ-агентам используй:
- **`doc_ai/TASKS_FOR_AI_AGENTS.md`** — детальные правила формулирования задач
- **`AGENTS.md`** — общие правила для всего репозитория
- **Локальные `AGENTS.md`** в подкаталогах — специфичные правила для компонентов

**Формат задачи должен включать:**
1. Контекст (где в архитектуре, какие документы читать)
2. Цель (что должно измениться)
3. Входные данные (пути к файлам, примеры)
4. Ожидаемый результат (конкретные файлы, функции)
5. Ограничения (что нельзя менять)
6. Критерии приёмки (как проверить)

## Детальные правила и инварианты проекта

Ниже сводка конкретных инвариантов, извлечённых из `doc_ai/`. При работе над задачей **всегда** уточняй детали в соответствующей спецификации — это компактная памятка, а не замена документов.

### AE3 (automation-engine) — критичные инварианты

- **Канонический runtime — `ae3lite/`**, монолитный AE удалён; `ae2lite` удалён. См. `doc_ai/04_BACKEND_CORE/ae3lite.md`.
- Прямой MQTT-publish из AE или Laravel **запрещён** — только через `history-logger` `POST /commands`.
- **Одна активная execution task на зону** — гарантируется partial unique index + `ZoneLease`.
- Единственный внешний ingress AE3: `POST /zones/{id}/start-cycle` (+ `POST /zones/{id}/start-irrigation` для штатного полива).
- Единственный internal status endpoint: `GET /internal/tasks/{task_id}`.
- Runtime AE3 читает zone state **напрямую из PostgreSQL read-model** — никаких runtime HTTP-запросов к Laravel.
- Успешный terminal outcome mutating-команды — только `DONE`; `NO_EFFECT|ERROR|INVALID|BUSY|TIMEOUT|SEND_FAILED` = fail для v1.
- Task FSM: `pending → claimed → running → waiting_command → completed/failed`. Two-tank requeue: `running → pending` через `requeue_pending`.
- Переключение `zones.automation_runtime='ae3'` **запрещено** при активной task или active lease.
- Hardcoded default targets **запрещены** — отсутствие target во фразе рецепта = `PlannerConfigurationError` (fail-closed).
- `ae3lite/*` **не импортирует** legacy runtime пакеты.
- Error codes: `ae3_task_create_conflict`, `ae3_lease_claim_failed`, `ae3_complete_transition_failed`, `ae3_requeue_failed`, `cycle_start_blocked_nodes_unavailable`, `irr_state_unavailable`, `two_tank_prepare_targets_unavailable`.

### Команды к узлам и валидация

- Канонические `cmd` значения: `run_pump`, `dose`, `set_relay`, `set_pwm`, `calibrate`, `test_sensor`, `restart`, `state`.
- Статусы команд: `ACK`, `DONE`, `ERROR`, `INVALID`, `BUSY`, `NO_EFFECT`, `TIMEOUT`. Статусы `ACCEPTED`/`FAILED` **запрещены**.
- Timestamp валидация: `abs(now - ts) < 10 секунд` на всех уровнях.
- HMAC-SHA256: canonical JSON с lexicographic sort ключей, порядок массивов сохранён, без whitespace, числа в формате cJSON, UTF-8, unescaped slashes. `node_secret` — 32 байта на узел.
- `command_response.ts` — в **миллисекундах**.
- Ограничения: pH dose interval ≥ 20 сек, EC dose ≥ 10 сек, max pump duration = 60000 мс, доза = 0.1–5.0 мл.
- `test_sensor` обязателен для SENSOR-каналов; `restart` и `state` обязательны для всех узлов.
- 3 последовательных `no-effect` для одного `pid_type` → alert + fail-closed correction window. Обычные correction attempts и `no-effect` — независимые лимиты.

### MQTT — дополнительные правила

- QoS=1, Retain=false для `telemetry/commands/responses/config_report`; Retain=true для `status/lwt`.
- Порядок сегментов топика менять **запрещено**; смешивать системные и зональные топики (писать телеметрию в `hydro/system/`) **запрещено**.
- До получения `hydro/time/response` узел **не должен** публиковать telemetry/status/event с полем `ts`.
- Для 2-бакового контура (`level_switch`) узел обязан публиковать `event_code="level_switch_changed"` + поля `channel`, `state`, `initial`, `snapshot`.
- Event code → `zone_events.type`: UPPERCASE + замена `[^A-Z0-9]` → `_`, усечение до 255 с suffix `_{SHA1_10}`.
- MQTT как произвольное «лог-хранилище» больших JSON **запрещено**.

### Телеметрия и Effective Targets

- Обязательные поля telemetry: `metric_type` (UPPERCASE), `value`, `ts` (в **секундах**). Опциональные: `unit`, `raw`, `stub`, `stable`, `flow_active`, `corrections_allowed`.
- Python резолвит `sensor_id` через таблицу `sensors` по (`zone_id, node_id, metric_type, channel, scope`).
- **pH/EC target|min|max** — canonical source **только** active recipe phase; `cycle.phase_overrides` и `zone.logic_profile` **не переопределяют** chemical setpoints. Отсутствие target = ошибка конфигурации (fail-closed).
- Effective targets **не кэшируются** постоянно — пересчитываются при смене фазы, update recipe, изменении параметров зоны.
- `volume_ml` в effective targets остаётся доменным полем — AE3 не переводит автоматически мл→длительность без калибровок.
- Для `lighting.mode="TASK"` параметры irrigation (`mode/interval/duration`) — recipe-owned, zone override игнорируется.

### Политика хранения данных

| Категория | Hot (online) | Warm/agg | Cold archive |
|-----------|--------------|----------|--------------|
| Сырая телеметрия | 30 дней (Laravel `telemetry:cleanup-raw`) / 90 дней (Python `RETENTION_SAMPLES_DAYS`) | agg_1m, agg_1h, daily 6-12 мес | 5 лет S3 |
| Команды | 90 дней | — | 3 года |
| События | 180 дней | — | 5 лет |
| Алерты | 365 дней | — | автоудаление resolved/acknowledged/TTL |
| Логи | 7-30 дней | 1 год (gz) | 5 лет cold |

- `telemetry:aggregate` — каждые 15 мин (Laravel, `ON CONFLICT DO NOTHING`); Python — `ON CONFLICT DO UPDATE`.
- При удалении зоны: `telemetry_last`/raw удаляются; agg/daily **анонимизируются**; events/logs **архивируются**.
- Обновлять retention одновременно в `routes/console.php` (Laravel) и `.env` (Python).

### Backend / Laravel — специфика

- **Версии (authoritative):** PHP 8.2.29, Laravel 12, Inertia 2, Vue 3, Tailwind 3, PHPUnit 11.
- **Структура Laravel 11+:** `bootstrap/app.php` для middleware/exceptions/routing, `bootstrap/providers.php` для service providers; нет `app/Console/Kernel.php` — команды в `app/Console/Commands/` auto-register.
- **Валидация:** всегда через Form Request classes, **не inline** в контроллере.
- **БД доступ:** использовать Eloquent models/relationships, **избегать** `DB::`; `Model::query()`. Eager loading для N+1.
- **Config:** `env()` только в config-файлах; в коде — `config('app.name')`.
- **Routing:** `route()` + named routes, не хардкод URL.
- **Inertia:** компоненты в `resources/js/Pages`; `Inertia::render()` вместо Blade; `<Form>` компонент / `useForm` helper; использовать v2-фичи (polling, prefetching, deferred props, lazy loading).
- **Тяжёлые задачи:** через `ShouldQueue`; тяжёлую ML/симуляцию в Laravel **не встраивать** — выносить в Python-сервис.
- **Вызовы Python-сервиса** централизованы, не размазаны по контроллерам.
- **PHP стиль:** `vendor/bin/pint --dirty` перед финализацией; constructor property promotion; обязательные return types; `{}` даже для однострочных control structures; PHPDoc вместо inline комментариев; enum keys в TitleCase.
- **Тесты:** PHPUnit (не Pest); каждое изменение покрывать тестом; запускать `--filter=`; при изменении column в migration **включать все предыдущие атрибуты**.
- **Artisan:** `make:` команды для всех файлов; `--no-interaction` + `--options`; `list-artisan-commands` перед вызовом.

### Frontend / Vue — специфика

- **`<script setup>`** синтаксис, **не** Options API.
- Компонент Vue **один root-элемент**; навигация через `router.visit()`/`<Link>`, не classic links.
- Shared-компоненты зоны переиспользуются и в `/setup/wizard`, и в zone edit — один UX.
- Events UI группирует по causal-context: `correction_window_id → task_id → snapshot_event_id/caused_by_event_id`.
- Automation tab **не смешивает** operator flow с scheduler/execution detail view.
- Manual-step controls рендерятся **только** из `allowed_manual_steps`, не из хардкода.
- **Роли:** Dashboard рендерится по роли (`AgronomistDashboard`/`AdminDashboard`/`EngineerDashboard`/`OperatorDashboard`/`ViewerDashboard`); использовать `useRole()` composable; пункты меню условно рендерятся, не удаляются.
- **Стили:** Tailwind 3 classes (только v3-совместимые); gap utilities вместо margins; все новые страницы поддерживают dark mode (`dark:` классы); dark theme — по умолчанию.
- **Deferred props** — всегда с animated skeleton empty state.
- **Тесты:** Vitest + Vue Test Utils; один тест = одна проверка; моки минимальные (только внешние зависимости); Playwright E2E — реальные HTTP/WebSocket.

### Прошивки ESP32 / C

- Язык **только C99**, C++ **запрещён**. ESP-IDF 5.x.
- **Нейминг:** файлы `snake_case.{c,h}`, функции/переменные `snake_case` с префиксом компонента, типы `snake_case_t`, макросы `UPPER_SNAKE_CASE`.
- **Стиль:** 4 пробела (табы запрещены), K&R (открывающая `{` на той же строке).
- **Обработка ошибок:** все функции возвращают `esp_err_t`, никаких тихих провалов, логировать контекст.
- **Логирование:** в каждом компоненте `static const char *TAG = "component_name"`; уровни: `ESP_LOGE` (ошибки), `LOGW` (потенциальные), `LOGI` (ключевые), `LOGD` (отладка), `LOGV` (подробно). Секреты/пароли **не логировать**.
- **Публичный API** каждого компонента — в `include/<component_name>.h`.
- **FreeRTOS:** одна логическая подсистема = одна task (`wifi_task`, `mqtt_task`, `sensor_task`); обмен через очереди/Event Groups; глобальные разделяемые структуры без mutex **запрещены**.
- **I2C:** один общий `hw_i2c` компонент с **mutex** для сериализации доступа.
- **NVS:** все операции — только через `node_config` компонент.
- **Тестируемость:** бизнес-логика независима от железа (интерфейсы/колбэки).
- **Запрет динамического выделения памяти** в горячих путях.

### NodeConfig

- JSON-конфиг с обязательными: `node_id`, `version`, `type`, `gh_uid`, `zone_uid`, `channels`, `wifi`, `mqtt`. Версия формата — **3**.
- Каналы: `SENSOR` (с `metric`, `poll_interval_ms`, `unit`, `precision`) и `ACTUATOR` (с `actuator_type`, `safe_limits`).
- Калибровка pH — 2-3 точки (raw/value); EC — K-value + temperature compensation.
- `fail_safe_guards` для `irrig` — **зеркало** значений из `zone.logic_profile`.
- Узел обязан валидировать NodeConfig, применять локально и публиковать `config_report` как ACK.
- HMAC подпись конфига — timestamp не старше 60 секунд (команды — не старше 30).

### Безопасность

- Каждый узел имеет уникальный `node_secret` (32 байта) для HMAC.
- OTA защищена: SHA256, версия, signed URL, HMAC запроса.
- MQTT должен быть закрыт для внешних сетей; Wi-Fi — скрытый, WPA2/WPA3.
- Pessimistic locking (`SELECT FOR UPDATE`) при публикации конфигов; PostgreSQL advisory lock для дедупликации; кэш-дедупликация 60 сек.
- Rate limiting: 60 req/min/IP стандартно; регистрация узлов — 10 req/min/node_uid + burst 120/min/IP; IP whitelist (`services.node_registration.allowed_ips`).
- Docker network — `internal: true` для отключения внешней доступности.
- **Роли/авторизацию (`auth/roles`) не менять** без явной необходимости и тестов.

### Локальные AGENTS.md (обязательно читать при работе в подкаталоге)

- `backend/laravel/docs/AGENTS.md` — подробные Laravel-правила (версии, Eloquent, Inertia, тесты, стиль).
- `backend/services/AGENTS.md` — разделение Laravel scheduler-dispatch ↔ AE ↔ history-logger; запреты на прямой MQTT из AE/Laravel.
- `backend/services/automation-engine/AGENT.md` — canonical AE3-Lite контракт, error codes, task FSM, команды для тестов.

### Документация — конвенции

- Основной язык — русский; английские термины только как технические идентификаторы.
- Стандартные разделы: Цель, Контекст, Требования, Архитектура/Дизайн, Протоколы/Интерфейсы, Сценарии использования, Ограничения и риски, Планы развития.
- Версия/дата/автор — в заголовке, **не** в имени файла.
- Структура папок `01_...12_` — единая живая версия, **не** создавать `v3/v4` папки.
- Новые файлы логически попадают в существующие папки; если места нет — сначала обновить архитектурный документ с обоснованием.
- **Документацию (.md)** создавать только по явному запросу пользователя.

### Где искать детали правил (source of truth)

| Тема | Документ |
|------|----------|
| AE3 runtime и контракт | `doc_ai/04_BACKEND_CORE/ae3lite.md`, `AE3_RUNTIME_EVENT_CONTRACT.md` |
| Irrigation failsafe, E-STOP | `doc_ai/04_BACKEND_CORE/AE3_IRR_FAILSAFE_AND_ESTOP_CONTRACT.md` |
| Level switch events | `doc_ai/04_BACKEND_CORE/AE3_IRR_LEVEL_SWITCH_EVENT_CONTRACT.md` |
| MQTT топики/payload | `doc_ai/03_TRANSPORT_MQTT/MQTT_NAMESPACE.md`, `MQTT_SPEC_FULL.md`, `BACKEND_NODE_CONTRACT_FULL.md` |
| Валидация команд | `doc_ai/03_TRANSPORT_MQTT/COMMAND_VALIDATION_ENGINE.md` |
| Модель данных | `doc_ai/05_DATA_AND_STORAGE/DATA_MODEL_REFERENCE.md` |
| Retention | `doc_ai/05_DATA_AND_STORAGE/DATA_RETENTION_POLICY.md` |
| Коррекция pH/EC | `doc_ai/06_DOMAIN_ZONES_RECIPES/CORRECTION_CYCLE_SPEC.md` |
| Effective targets | `doc_ai/06_DOMAIN_ZONES_RECIPES/EFFECTIVE_TARGETS_SPEC.md` |
| Error codes | `doc_ai/04_BACKEND_CORE/ERROR_CODE_CATALOG.md` |
| Frontend UI/UX | `doc_ai/07_FRONTEND/FRONTEND_UI_UX_SPEC.md`, `ROLE_BASED_UI_SPEC.md` |
| ESP32 C-стиль | `doc_ai/02_HARDWARE_FIRMWARE/ESP32_C_CODING_STANDARDS.md` |
| NodeConfig спец | `doc_ai/02_HARDWARE_FIRMWARE/NODE_CONFIG_SPEC.md` |
| Безопасность | `doc_ai/08_SECURITY_AND_OPS/SECURITY_ARCHITECTURE.md`, `AUTH_SYSTEM.md` |
| AI-гайды (чек-листы) | `doc_ai/10_AI_DEV_GUIDES/AI_ASSISTANT_DEV_GUIDE.md`, `BACKEND_LARAVEL_PG_AI_GUIDE.md`, `DATABASE_SCHEMA_AI_GUIDE.md` |

## Разработка прошивок ESP-IDF

### Настройка окружения ESP-IDF

**Расположение:** `/home/georgiy/esp/esp-idf/`
**Версия:** v5.5.2

Перед работой с прошивками необходимо активировать окружение ESP-IDF:

```bash
# Активация окружения ESP-IDF
source /home/georgiy/esp/esp-idf/export.sh

# Или короткий алиас (добавь в ~/.bashrc или ~/.zshrc для удобства):
alias get_idf='source /home/georgiy/esp/esp-idf/export.sh'
```

После активации окружения станут доступны команды `idf.py` и все необходимые инструменты компиляции.

### Сборка прошивки

```bash
source /home/georgiy/esp/esp-idf/export.sh  # активировать окружение

cd firmware/nodes/<имя_ноды>
idf.py build
idf.py flash monitor

# Другие команды: menuconfig, erase-flash
```

### Типы узлов

- `pump_node` — управление насосом полива с мониторингом тока
- `ph_node` — измерение pH и управление дозирующим насосом
- `ec_node` — измерение EC/TDS и дозирование питательных веществ
- `climate_node` — мониторинг температуры, влажности, CO2
- `light_node` — управление освещением (PWM/адресные светодиоды)
- `relay_node` — универсальное управление реле

## Разработка Frontend

Расположен в `backend/laravel/resources/js/`

### Ключевые технологии
- Vue 3 (Composition API)
- TypeScript
- Inertia.js (SSR)
- Pinia (управление состоянием)
- Tailwind CSS
- ECharts (визуализации)

### Разработка

```bash
cd backend/laravel

# Dev сервер с HMR
npm run dev

# Сборка для production
npm run build

# Проверка типов
npm run typecheck

# Линтинг
npm run lint
```

### Стратегия тестирования

См. `doc_ai/07_FRONTEND/FRONTEND_TESTING.md` для деталей:
- **Unit тесты:** Vitest для утилит и composables
- **Компонентные тесты:** Vitest + Vue Test Utils
- **Интеграционные тесты:** Тестирование Inertia страниц
- **E2E тесты:** Playwright для критических пользовательских сценариев

## Работа с AI агентами

См. `doc_ai/TASKS_FOR_AI_AGENTS.md` и `AGENTS.md` для детальных руководств.

**Ключевые принципы:**
- Всегда сначала проверяй документацию в `doc_ai/`
- Для нетривиальных задач создавай `.md` файл с формализованными требованиями
- Будь конкретным: указывай файлы, функции, структуры данных, форматы сообщений
- Результаты должны проверяться людьми или валидационными агентами

## Стратегия тестирования

### Тесты протокольных контрактов

```bash
make protocol-check
```

Это запускает:
- Проверки соответствия runtime схем
- Контрактные тесты для MQTT сообщений
- Тесты валидации протокола
- Chaos тесты (неблокирующие)
- Тесты WebSocket событий

### Симулятор узлов

Расположен в `tests/node_sim/` — симулирует ESP32 узлы для интеграционного тестирования без физического оборудования.

### E2E тесты

Расположены в `tests/e2e/` — сквозное тестирование сценариев.

## Мониторинг и наблюдаемость

### Проверка здоровья системы

```bash
./backend/scripts/check_monitoring.sh
```

### Дашборды Grafana

Доступ по http://localhost:3000 (по умолчанию: admin/admin):
- System Overview — здоровье сервисов
- Zone Telemetry — графики pH/EC/температуры
- Node Status — подключение узлов
- Alerts Dashboard — активные алерты
- Commands & Automation — статистика команд

## Важные замечания

- **Backend команды** всегда запускаются внутри Docker контейнеров через `docker compose exec`
- **MQTT_EXTERNAL_HOST:** В dev по умолчанию `host.docker.internal`. Для реальных ESP32 — IP адрес хоста
- **Миграции:** Запускай `make migrate` после получения изменений схемы
- **Изменения протокола:** Всегда обновляй контрактные тесты (`make protocol-check`)

## Troubleshooting

### Backend не запускается
- Проверь доступность портов (8080, 9000, 9300, 9401, 9405, 1883, 5432)
- Убедись, что Docker daemon запущен
- Проверь логи: `docker compose -f backend/docker-compose.dev.yml logs`

### Сборка прошивки падает
- **Окружение ESP-IDF не активировано:** Запусти `source /home/georgiy/esp/esp-idf/export.sh`
- **Команда idf.py не найдена:** Проверь, что ESP-IDF установлен в `/home/georgiy/esp/esp-idf/` и активирован
- **Ошибки компиляции:** Проверь зависимости компонентов в CMakeLists.txt
- **Ошибки с I2C:** Проверь, что I2C адреса соответствуют твоему оборудованию

### Тесты падают
- Убедись, что dev стек запущен: `make up`
- Проверь, что база данных заполнена: `make seed`
- Проверь доступность MQTT брокера

### Проблемы с подключением MQTT
- Проверь логи MQTT брокера: `docker compose -f backend/docker-compose.dev.yml logs mqtt`
- Проверь учетные данные в конфигурации mosquitto
- Для ESP32: убедись, что MQTT_EXTERNAL_HOST установлен правильно

## Формат ссылок на файлы

При ссылках на места в коде в коммитах или документации используй формат:
```
путь_к_файлу:номер_строки
```

Пример: `src/services/process.ts:712`

Этот формат кликабелен в большинстве IDE и инструментов.
