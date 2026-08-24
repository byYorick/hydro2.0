Python Core (MVP 1a)

## Архитектура

Канон: `doc_ai/04_BACKEND_CORE/PYTHON_SERVICES_ARCH.md`. Этот README — указатель, **не** Source of Truth.

## Структура

- **Общая библиотека:** `common/` (env, db, mqtt, schemas, commands)
- **Сервисы:**
  - `mqtt-bridge` — ops leftover / probe (порт 9000): `GET /metrics`, `GET /bridge/nodes/{uid}/live-status`. **Не** мост команд.
  - `history-logger` — подписка на MQTT, запись телеметрии в PostgreSQL, **единственная точка публикации команд в MQTT** (порт 9300)
  - `automation-engine` — AE3 рантайм зон, wake-up `start-cycle`, управление mode/manual-step, публикация команд через history-logger REST API (порт 9405: REST API + `/metrics/`)
  - `Laravel scheduler-dispatch` — owner planning/dispatch intents и wake-up в `automation-engine` (через `automation:dispatch-schedules`)
  - реестр устройств — Laravel (отдельного Python `device-registry` нет)

## Переменные окружения (dev)

Через `docker-compose.dev.yml`:
- `MQTT_HOST=mqtt`, `PG_HOST=db`, `PG_DB=hydro_dev`, `PG_USER=hydro`, `PG_PASS=hydro`
- `LARAVEL_API_URL=http://laravel` (для automation-engine), `LARAVEL_API_TOKEN=...`

## Запуск

Из корня репозитория:
```bash
docker compose -f backend/docker-compose.dev.yml up -d --build
```

## Тесты

Единый прогон по всем Python-сервисам (избегает конфликтов импортов между сервисами):
```bash
PG_HOST=localhost PG_PORT=5432 PG_DB=hydro_dev PG_USER=hydro PG_PASS=hydro \
PYTHONPATH=/home/georgiy/esp/hydro/hydro2.0/backend/services \
.venv/bin/python -m pytest -rs --import-mode=importlib
```

Если нужны локальные прогоны по сервисам, запускайте из соответствующей папки сервиса.

## Проверка сервисов

### Команды — только history-logger (порт 9300)

Канон публикации команд:

```bash
POST http://localhost:9300/commands
```

Не вызывать `POST http://localhost:9000/bridge/zones/{zone_id}/commands` — это не command path (`mqtt-bridge` отвечает 410, роуты живут до P1).

### mqtt-bridge (ops probe, порт 9000)

- `GET http://localhost:9000/metrics`
- `GET http://localhost:9000/bridge/nodes/{uid}/live-status`

### REST API Endpoints

**History-Logger (порт 9300):**
- `POST /commands` — канонический endpoint для команд
- `POST /zones/{zone_id}/commands` - команды для зоны
- `POST /nodes/{node_uid}/commands` - команды для ноды
- `POST /nodes/{uid}/config` — канон публикации NodeConfig
- `GET /health` - health check

**Automation-Engine (порт 9405):**
- `POST /zones/{id}/start-cycle` - каноничный wake-up цикла
- `GET /zones/{id}/state` - runtime state зоны
- `GET /zones/{id}/control-mode` - режим и доступные manual-step
- `POST /zones/{id}/control-mode` - смена режима
- `POST /zones/{id}/manual-step` - ручной шаг
- `GET /health/live` - liveness
- `GET /health/ready` - readiness

### Prometheus metrics
- history-logger: `http://localhost:9300/metrics`
- automation-engine: `http://localhost:9405/metrics/`

## Архитектура команд

**Централизованная публикация команд:**
```
Laravel Scheduler → POST /zones/{id}/start-cycle → Automation-Engine → REST (9300) → History-Logger → MQTT → Ноды
```

**Важно:** 
- `history-logger` — **единственная точка публикации команд в MQTT**
- `automation-engine` публикует device-команды только через history-logger REST API, не напрямую в MQTT
- Это обеспечивает единую точку логирования и мониторинга команд

## Документация

- Архитектура Python-сервисов (канон): `../../doc_ai/04_BACKEND_CORE/PYTHON_SERVICES_ARCH.md`
- Changelog: `CHANGELOG.md`
- Общая архитектура backend: `../../doc_ai/04_BACKEND_CORE/BACKEND_ARCH_FULL.md`
- MQTT спецификация: `../../doc_ai/03_TRANSPORT_MQTT/MQTT_SPEC_FULL.md`
