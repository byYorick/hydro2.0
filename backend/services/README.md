Python Core (MVP 1a)

## Архитектура

См. подробную документацию: `PYTHON_SERVICES_ARCH.md`

## Структура

- **Общая библиотека:** `common/` (env, db, mqtt, schemas, commands)
- **Сервисы:**
  - `mqtt-bridge` — FastAPI мост REST→MQTT (порт 9000)
  - `history-logger` — подписка на MQTT, запись телеметрии в PostgreSQL, **единственная точка публикации команд в MQTT** (порт 9300)
  - `automation-engine` — контроллер зон, проверка targets, публикация команд через history-logger REST API (порты 9401/metrics, 9405/REST API)
  - `scheduler` — расписания поливов/света из recipe phases, публикация команд через automation-engine REST API (порт 9402)
  - `device-registry` — PLANNED (см. `device-registry/README.md`)

## Переменные окружения (dev)

Через `docker-compose.dev.yml`:
- `MQTT_HOST=mqtt`, `PG_HOST=db`, `PG_DB=hydro_dev`, `PG_USER=hydro`, `PG_PASS=hydro`
- `LARAVEL_API_URL=http://laravel` (для automation-engine), `LARAVEL_API_TOKEN=...`

## Запуск

Из корня репозитория:
```bash
docker compose -f backend/docker-compose.dev.yml up -d --build
```

## Проверка сервисов

### mqtt-bridge
```bash
POST http://localhost:9000/bridge/zones/{zone_id}/commands
{
  "type": "FORCE_IRRIGATION",
  "params": {"duration_sec": 5},
  "greenhouse_uid": "gh-1",
  "node_id": 1,
  "channel": "pump_in"
}
```

### REST API Endpoints

**History-Logger (порт 9300):**
- `POST /commands` - универсальный endpoint для команд
- `POST /zones/{zone_id}/commands` - команды для зоны
- `POST /nodes/{node_uid}/commands` - команды для ноды
- `GET /health` - health check

**Automation-Engine (порт 9405):**
- `POST /scheduler/command` - прием команд от scheduler
- `GET /health` - health check

### Prometheus metrics
- history-logger: `http://localhost:9301/metrics`
- automation-engine: `http://localhost:9401/metrics`
- scheduler: `http://localhost:9402/metrics`

## Архитектура команд

**Централизованная публикация команд:**
```
Scheduler → REST (9405) → Automation-Engine → REST (9300) → History-Logger → MQTT → Ноды
```

**Важно:** 
- `history-logger` — **единственная точка публикации команд в MQTT**
- `automation-engine` и `scheduler` публикуют команды через REST API, не напрямую в MQTT
- Это обеспечивает единую точку логирования и мониторинга команд

## Документация

- Архитектура Python-сервисов: `PYTHON_SERVICES_ARCH.md`
- Changelog: `CHANGELOG.md`
- Общая архитектура backend: `../../doc_ai/04_BACKEND_CORE/BACKEND_ARCH_FULL.md`
- MQTT спецификация: `../../doc_ai/03_TRANSPORT_MQTT/MQTT_SPEC_FULL.md`

