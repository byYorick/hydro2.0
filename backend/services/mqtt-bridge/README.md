# mqtt-bridge

Ops/probe FastAPI-сервис (порт **9000**). **Не** публикует device-команды в MQTT — канон команд: `history-logger` `POST /commands`.

## Endpoints

| Метод | Путь | Назначение |
|-------|------|------------|
| GET | `/metrics` | Prometheus |
| GET | `/bridge/nodes/{node_uid}/live-status` | MQTT probe online/retained status (без чтения Laravel DB) |
| POST | `/bridge/nodes/{node_uid}/config` | Legacy/ops push NodeConfig в MQTT (**канон publish:** HL `POST /nodes/{uid}/config` из Laravel `PublishNodeConfigJob`) |
| POST | `/bridge/zones/{zone_id}/commands` | **410** `endpoint_deprecated_use_history_logger` |
| POST | `/bridge/nodes/{node_uid}/commands` | **410** `endpoint_deprecated_use_history_logger` |

Auth: Bearer `PY_API_TOKEN` (localhost без токена — только dev).

См. `doc_ai/04_BACKEND_CORE/PYTHON_SERVICES_ARCH.md` §2.4.
