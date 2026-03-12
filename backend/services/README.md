Python Core (MVP 1a)

## Архитектура

См. подробную документацию: `PYTHON_SERVICES_ARCH.md`

## Структура

- **Общая библиотека:** `common/` (env, db, mqtt, schemas, commands)
- **Сервисы:**
  - `mqtt-bridge` — FastAPI мост REST→MQTT (порт 9000)
  - `history-logger` — подписка на MQTT, запись телеметрии в PostgreSQL
  - `automation-engine` — контроллер зон, проверка targets, публикация команд (порт 9401)
  - `scheduler` — расписания поливов/света из recipe phases (порт 9402)
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

### Prometheus metrics
- automation-engine: `http://localhost:9401/metrics`
- scheduler: `http://localhost:9402/metrics`

## Документация

- Архитектура Python-сервисов: `PYTHON_SERVICES_ARCH.md`
- Общая архитектура backend: `doc_ai/04_BACKEND_CORE/BACKEND_ARCH_FULL.md`
- MQTT спецификация: `doc_ai/03_TRANSPORT_MQTT/MQTT_SPEC_FULL.md`

