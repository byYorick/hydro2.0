# GROK.md
# Правила для Grok (Hydro 2.0)

**Дата обновления:** 2026-07-15  
**Версия:** 1.0  
**Статус:** Свод правил для Grok Build / Grok agent (аналог `CLAUDE.md` + выжимка `AGENTS.md`)

> Этот файл — operational guide для Grok.  
> Общие правила репозитория: `AGENTS.md`.  
> Подробный operational guide для Claude Code: `CLAUDE.md` (Grok тоже может его читать).  
> Source of truth документации: **`doc_ai/`**.

---

## 0) Язык и поведение

- **Всегда общайся с пользователем на русском.**
- Английский — только код, идентификаторы API/MQTT, имена файлов, технические термины (`docker compose`, `pytest`, `HMAC`).
- Сообщения коммитов и обновления документации — **на русском**.
- Не придумывать архитектуру заново; не игнорировать `doc_ai/`.
- Если данных мало — **спросить**, а не домысливать.
- Для сложных задач: сначала **план + список файлов**, потом код.
- Если изменение ломает пайплайн `ESP32 → MQTT → Python → PG → Laravel → Vue` или неочевидно — **остановиться и спросить подтверждение**.
- Документацию (`.md`) создавать/расширять **только по явному запросу** пользователя (кроме обязательных обновлений спецификаций при изменении протоколов/данных).

---

## 1) Приоритет правил

1. Корневой `AGENTS.md` / `GROK.md` / `CLAUDE.md`
2. Спецификации слоя в `doc_ai/0X_.../*`
3. Локальный `AGENTS.md` / `AGENT.md` в подкаталоге
4. Гайды ИИ в `doc_ai/10_AI_DEV_GUIDES/`

При конфликте — **более строгое** требование; при сомнении — спросить пользователя.

**Локальные AGENTS (обязательно читать в подкаталоге):**

| Путь | О чём |
|------|--------|
| `backend/laravel/docs/AGENTS.md` | Laravel: Eloquent, Inertia, тесты, стиль |
| `backend/services/AGENTS.md` | scheduler-dispatch ↔ AE ↔ history-logger; запрет MQTT из AE/Laravel |
| `backend/services/automation-engine/AGENT.md` | AE3-Lite: FSM, error codes, тесты |

Grok также подхватывает правила из `.grok/rules/*.md`.

---

## 2) Обязательный минимум перед работой

1. Открыть релевантные 2–3 документа слоя из `doc_ai/` (не весь монорепо).
2. Проверить локальный `AGENTS.md` / `AGENT.md` в каталоге задачи.
3. Backend / Python / БД / e2e — команды **внутри Docker**.
4. Прошивки ESP32 — **вне Docker**, ESP-IDF: `source /home/georgiy/esp/esp-idf/export.sh`.

**Минимум документов (если не знаешь, с чего начать):**

- `doc_ai/INDEX.md`
- `doc_ai/SYSTEM_ARCH_FULL.md`
- `doc_ai/ARCHITECTURE_FLOWS.md`
- `doc_ai/DEV_CONVENTIONS.md`

---

## 3) Обзор проекта

Монорепозиторий системы управления гидропонной теплицей:

- **ESP32 firmware** — pH, EC, climate, pump, light, relay
- **Laravel 12** — API Gateway + Inertia.js + Vue 3
- **Python services** — mqtt-bridge, history-logger, automation-engine (AE3)
- **PostgreSQL + TimescaleDB** — телеметрия
- **MQTT** — связь узлов ↔ backend
- **Android app**, Docker/K8s, мониторинг

**Иерархия:** Теплица → Зоны → Узлы → Каналы.

**Канонический поток команд:**

```
Laravel scheduler-dispatch → Automation-Engine → History-Logger → MQTT → ESP32
```

**Критично:** только `history-logger` публикует команды в MQTT.  
Laravel и AE **не** публикуют MQTT напрямую.

---

## 4) Dev-команды (Make)

```bash
make up              # поднять dev-стек (backend/docker-compose.dev.yml)
make down            # остановить
make migrate         # миграции + DevBootstrapSeeder
make seed            # полный seed
make reset-db        # wipe hydro_dev + base users + restart runtime
make refresh         # жёсткий rebuild (удаляет volumes/images!) — осторожно
make test            # PHP + Python suite
make test-ae         # AE3 pytest на hydro_test (НЕ на hydro_dev)
make test-db-reset   # пересоздать hydro_test
make lint            # Pint
make protocol-check  # контракты протокола
make smoke           # короткий e2e smoke
make logs-core       # laravel + ae + hl + mqtt-bridge
make logs SERVICE=<name> TAIL=200
```

### Тесты по слоям

```bash
# Laravel
docker compose -f backend/docker-compose.dev.yml exec laravel php artisan test --filter=Name
make test-laravel LARAVEL_TEST_ARGS="tests/Feature/FooTest.php"

# AE3 (integration → только make test-ae, иначе мусор в hydro_dev)
make test-ae
make test-ae PYTEST_ARGS="-q test_ae3lite_probe_backoff.py"
make test-ae PYTEST_ARGS="-x -k test_name"

# history-logger / mqtt-bridge
make test-hl
make test-mqttb

# Frontend (из backend/laravel/)
npm run test && npm run typecheck && npm run lint
```

**Интеграционные AE-тесты** всегда через `make test-ae` (`PG_DB=hydro_test`).  
Быстрый `docker exec … pytest` — **только unit без БД**.

### Dev endpoints

| Сервис | URL |
|--------|-----|
| Laravel | http://localhost:8080 |
| mqtt-bridge | http://localhost:9000 |
| history-logger | http://localhost:9300 (metrics :9301) |
| automation-engine | http://localhost:9405 (metrics :9401) |
| Grafana | http://localhost:3000 |
| Prometheus | http://localhost:9090 |
| MQTT | localhost:1883 |
| PostgreSQL | localhost:5432, user/db `hydro` / `hydro_dev` |

---

## 5) Хост CLI (без docker exec)

На хосте доступны: `rg`, `fd`, `jq`, `yq`, `mosquitto_pub/sub`, `psql`, `http`, `gh`, `uv`, `idf.py` (после export ESP-IDF).

| Задача | Предпочтительно |
|--------|-----------------|
| Чтение БД | `psql -h localhost -U hydro -d hydro_dev -w` (`PGPASSWORD=hydro` или `~/.pgpass`) |
| MQTT debug | `mosquitto_sub -h localhost -t 'hydro/#' -v` |
| REST smoke | `http` / `curl` на порты выше |
| Python CLI tools | `uv tool install …` (системный pip заблокирован PEP 668) |
| artisan / pytest / composer / npm сервисов | **только Docker** |

MCP (если подключены): postgres, mqtt, redis, tasks — использовать по схеме через `search_tool` → `use_tool`.

---

## 6) Жёсткие запреты (не нарушать)

### 6.1 Пайплайн и команды

- ❌ MQTT publish из Laravel или automation-engine
- ✅ Команды только: `history-logger` `POST /commands` → MQTT
- ❌ Ломать топики/payload/схемы БД/Inertia props без миграции всего пайплайна
- ❌ Ручной DDL в PostgreSQL — только Laravel-миграции
- ❌ Менять `auth/roles` без явной нужды и тестов
- ❌ Динамическое выделение памяти в hot-path прошивок ESP32
- ❌ Hardcoded default targets pH/EC — fail-closed (`PlannerConfigurationError`)

### 6.2 MQTT

- Формат топика **строго**: `hydro/{gh}/{zone}/{node}/{channel}/{message_type}`
- QoS=1; Retain=false для telemetry/commands/responses/config_report; Retain=true для status/lwt
- `telemetry.ts` — **секунды**; `command_response.ts` — **миллисекунды**
- Timestamp skew: `abs(now - ts) < 10s`
- Новые `message_type` / `channel` — только с обновлением:
  - `doc_ai/03_TRANSPORT_MQTT/*`
  - `doc_ai/02_HARDWARE_FIRMWARE/NODE_CHANNELS_REFERENCE.md`
  - `doc_ai/05_DATA_AND_STORAGE/DATA_MODEL_REFERENCE.md`
  - обработчиков Python

### 6.3 Команды к узлам

Канонические `cmd`: `run_pump`, `dose`, `set_relay`, `set_pwm`, `calibrate`, `test_sensor`, `restart`, `state`.

Статусы: `ACK`, `DONE`, `ERROR`, `INVALID`, `BUSY`, `NO_EFFECT`, `TIMEOUT`.  
Запрещены: `ACCEPTED`, `FAILED`.

Mutating success terminal = только **`DONE`**.  
`NO_EFFECT|ERROR|INVALID|BUSY|TIMEOUT|SEND_FAILED` = fail (AE3 v1).

### 6.4 AE3 (automation-engine)

- Канонический runtime: **`ae3lite/`** (AE2/ae2lite удалены)
- Одна active execution task на зону (partial unique index + `ZoneLease`)
- External ingress: `POST /zones/{id}/start-cycle`, `POST /zones/{id}/start-irrigation`
- Internal status: `GET /internal/tasks/{task_id}`
- Runtime читает zone state **из PostgreSQL**, не через HTTP к Laravel
- `ae3lite/*` не импортирует legacy runtime
- Переключение `zones.automation_runtime='ae3'` запрещено при active task/lease
- Документы: `doc_ai/04_BACKEND_CORE/ae3lite.md`, `AE3_RUNTIME_EVENT_CONTRACT.md`, `AE3_IRR_FAILSAFE_AND_ESTOP_CONTRACT.md`

### 6.5 Телеметрия и targets

- Новые метрики → запись в **`telemetry_samples` и `telemetry_last`**
- pH/EC target|min|max — **только** active recipe phase (не `phase_overrides` / `logic_profile`)
- Sanity PID: pH ∈ [0, 14], EC ∈ [0, 20] mS/cm
- `pump_calibration.max_dose_ms` default **60000**; `last_dose_at` только после terminal `DONE`

### 6.6 Совместимость при смене протокола/данных

В commit/PR:

```
Compatible-With: Protocol 2.0, Backend >=3.0, Python >=3.0, Database >=3.0, Frontend >=3.0
```

Чек-лист: MQTT specs + DATA_MODEL + handlers + (если команды) HISTORY_LOGGER_API + (если pH/EC) CORRECTION/EFFECTIVE_TARGETS + frontend при смене API/props.

---

## 7) Зоны ответственности

| Компонент | ✅ Можно | ❌ Нельзя |
|-----------|---------|----------|
| **Laravel** | routes, models, migrations, pages, scheduler-dispatch | MQTT напрямую; ломать Inertia props без Vue |
| **Python services** | контроллеры, MQTT ingest, algorithms | менять форматы cmd в обход контракта; MQTT publish вне HL |
| **PostgreSQL** | поля/таблицы через миграции | ручной DDL; циклические FK; дроп обязательных полей |
| **MQTT** | новые message_type (с docs) | менять существующие топики/форматы |
| **Frontend** | UI/UX, composables | ломать props/types; Options API в новом коде |
| **Firmware** | C99 ESP-IDF, node_framework | C++; malloc в hot path |

---

## 8) Конвенции кода (кратко)

### Git

- Ветки: `main`, `feature/<описание>`
- Коммиты: `feat|fix|refactor|docs|test|chore: <описание на русском>`

### Laravel / PHP

- PHP 8.2, Laravel 12, Form Requests (не inline validation)
- Eloquent / `Model::query()`, избегать сырой `DB::` где возможно
- `env()` только в config; в коде — `config()`
- `vendor/bin/pint --dirty` / `make lint`
- Тесты: PHPUnit (не Pest)

### Python services

- PEP 8 + type hints + pytest
- Путь: `backend/services/`
- Команды к узлам — только через HL REST

### Vue 3

- `<script setup>`, Composition API, TypeScript strict
- Tailwind **v3**, dark mode (`dark:`), dark theme по умолчанию
- Vitest + Playwright; перед E2E — узкий scope и краткие рекомендации пользователю

### Firmware (C / ESP-IDF 5.x)

- Только **C99**, файлы `snake_case`, типы `snake_case_t`, макросы `UPPER_SNAKE_CASE`
- 4 пробела, K&R braces
- Всегда `esp_err_t`, ESP_LOG с `TAG`
- I2C через общий mutex; NVS только через `node_config`
- ESP-IDF path: `/home/georgiy/esp/esp-idf/`, version **v5.5.2**

### Документация first

1. Спека в `doc_ai/`  
2. Интерфейс / контракт  
3. Код  

---

## 9) Карта документации (куда смотреть)

| Тема | Документ |
|------|----------|
| Индекс | `doc_ai/INDEX.md` |
| Архитектура | `doc_ai/SYSTEM_ARCH_FULL.md`, `ARCHITECTURE_FLOWS.md` |
| AE3 | `doc_ai/04_BACKEND_CORE/ae3lite.md`, `AE3_*_CONTRACT.md` |
| HL API | `doc_ai/04_BACKEND_CORE/HISTORY_LOGGER_API.md` |
| MQTT | `doc_ai/03_TRANSPORT_MQTT/MQTT_SPEC_FULL.md`, `MQTT_NAMESPACE.md` |
| Данные | `doc_ai/05_DATA_AND_STORAGE/DATA_MODEL_REFERENCE.md` |
| pH/EC cycles | `doc_ai/06_DOMAIN_ZONES_RECIPES/CORRECTION_CYCLE_SPEC.md` |
| Effective targets | `doc_ai/06_DOMAIN_ZONES_RECIPES/EFFECTIVE_TARGETS_SPEC.md` |
| Frontend | `doc_ai/07_FRONTEND/FRONTEND_ARCH_FULL.md` |
| Firmware / NodeConfig | `doc_ai/02_HARDWARE_FIRMWARE/`, `firmware/NODE_CONFIG_SPEC.md` |
| Security | `doc_ai/08_SECURITY_AND_OPS/SECURITY_ARCHITECTURE.md` |
| AI guides | `doc_ai/10_AI_DEV_GUIDES/AI_ASSISTANT_DEV_GUIDE.md` |
| Задачи для ИИ | `doc_ai/TASKS_FOR_AI_AGENTS.md` |

---

## 10) Поведение Grok на типичных задачах

### 10.1 Фича / багфикс

1. Прочитать спеку слоя + локальный AGENTS  
2. План + список файлов (если нетривиально)  
3. Код + тесты  
4. Прогон узкого теста  
5. При касании протокола — обновить `doc_ai/` + Compatible-With  

### 10.2 Диагностика зоны / AE / irrigation

- Skills/commands: `two-tank-debug`, `zone-state`, `zone-audit`, `fix-stuck-zone`  
- Состояние: `zone_workflow_state`, `zone_events`, active task, intents  
- Не чистить БД «наугад» без подтверждения  

### 10.3 E2E / Playwright

**Сначала** сказать пользователю:

- узкий target (spec / `--grep`);
- анализ короткого хвоста ошибки;
- trace/video/screenshots только при падении.

**Потом** запускать.

### 10.4 Опасные действия — спрашивать

- `make refresh`, `reset-db`, `rm -rf`, drop DB, force-push, prod compose  
- Массовые DELETE в `zone_workflow_state` / ack alerts — только с подтверждением  

### 10.5 Ссылки на код

Формат: `path/to/file.ext:123`

---

## 11) Docker compose файлы

| Файл | Назначение |
|------|------------|
| `backend/docker-compose.dev.yml` | основной dev |
| `backend/docker-compose.dev.win.yml` | Windows |
| `backend/docker-compose.ci.yml` | CI |
| `backend/docker-compose.prod.yml` | prod |
| `tests/e2e/docker-compose.e2e.yml` | e2e |
| `infra/hil/docker-compose.hil.yml` | HIL |

---

## 12) Troubleshooting (быстро)

| Симптом | Что проверить |
|---------|----------------|
| Backend не встаёт | порты 8080/9000/9300/9405/1883/5432; `docker compose … logs` |
| idf.py не найден | `source /home/georgiy/esp/esp-idf/export.sh` |
| Тесты AE портят dev-БД | использовать `make test-ae`, не голый pytest в контейнере |
| MQTT с ESP32 | `MQTT_EXTERNAL_HOST` = IP хоста (не только host.docker.internal) |
| Миграции после pull | `make migrate` |

---

## 13) Связь с другими файлами правил

| Файл | Роль |
|------|------|
| `AGENTS.md` | канон правил для всех ИИ-агентов |
| `CLAUDE.md` | расширенный guide для Claude Code (совместим с Grok) |
| `GROK.md` | этот файл — свод для Grok |
| `.grok/rules/*.md` | автозагрузка Grok (жёсткие инварианты) |
| `doc_ai/` | единственный source of truth домена |

**Не дублировать** длинные спеки сюда — ссылаться на `doc_ai/` и читать по месту.
