# mqtt-bridge

Роль: **ops probe + Prometheus metrics**, не command/config path.

Ops/probe FastAPI-сервис (порт **9000**). Device-команды и NodeConfig в MQTT не публикует. Канон команд и config: `history-logger` (`POST /commands`, `POST /nodes/{uid}/config`).

## Endpoints

| Метод | Путь | Назначение |
|-------|------|------------|
| GET | `/metrics` | Prometheus |
| GET | `/bridge/nodes/{node_uid}/live-status` | MQTT probe online/retained status (без чтения Laravel DB) |

Auth: Bearer `PY_API_TOKEN` (localhost без токена — только dev).

См. `doc_ai/04_BACKEND_CORE/PYTHON_SERVICES_ARCH.md` §2.4.
