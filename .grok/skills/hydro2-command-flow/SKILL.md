---
name: hydro2-command-flow
description: "Канонический поток команд Hydro 2.0: Laravel scheduler-dispatch → AE3 (ae3lite) → history-logger POST /commands → MQTT → ESP32; fail-closed и HMAC. Используй при любых изменениях публикации команд, MQTT publish, HL API, AE wake/ingress, расписаний или отладке «команда не дошла до узла»."
metadata:
  type: workflow
  lifecycle: active
  version: "0.2.0"
---

# hydro2-command-flow

## Когда применять
Любая задача про отправку команд на узлы, «кто публикует в MQTT», HL `/commands`, AE3 wake, scheduler intents.

## Канон потока
```
Laravel scheduler-dispatch → Automation-Engine (ae3lite) → history-logger POST /commands → MQTT → ESP32
```
Единственная точка publish команд в MQTT — **history-logger**. Laravel и automation-engine **не** публикуют MQTT.

## Hard rules (defer)
Сверяй с `.grok/rules/hydro-hard-rules.md` и корневым `AGENTS.md`. При конфликте с внешними skills — **жёсткие правила Hydro побеждают**.

## Override внешних skills
- `docker-local-dev` — не поднимай digital-twin / feature-builder / node-emulator без явного запроса; default `make up` = core.
- `review-and-ship` — не force-push / reset-db / prod без подтверждения пользователя.
- `run-smoke-tests` — Playwright/smoke не заменяют `make test-ae` / HL/MQTT контрактные проверки.

## Источники (читать 2–3 по задаче)
- `doc_ai/ARCHITECTURE_FLOWS.md`
- `doc_ai/01_SYSTEM/DATAFLOW_FULL.md`
- `doc_ai/04_BACKEND_CORE/HISTORY_LOGGER_API.md`
- `doc_ai/03_TRANSPORT_MQTT/COMMAND_VALIDATION_ENGINE.md`
- `backend/services/AGENTS.md`
- `backend/services/automation-engine/AGENT.md`
- `backend/services/history-logger/command_service.py`, `command_routes.py`

## Инварианты
1. Команды к узлам только через HL `POST /commands`.
2. Fail-closed: при ошибках проверки writer-state / недоступности критичных сигналов — не «угадывать» ON.
3. HMAC подписи команд добавляются в HL (см. `hydro2-mqtt-security`).
4. Не ломать пайплайн `ESP32 → MQTT → Python → PG → Laravel → Vue` без миграции всего стека.
5. Новые Python-сервисы / AE3 `task_type` — только по явному запросу.

## Чеклист перед правкой
1. Локальный AGENTS/AGENT в подкаталоге сервиса.
2. Спека слоя из `doc_ai/`.
3. Убедиться, что новый код не делает `mosquitto`/`paho` publish вне HL.

## Актуализация 2026-11-06

- mqtt-bridge command/config routes удалены (404); metrics/live-status не являются командным API.
- Для runtime-bug проследи intent → ae_tasks → ae_commands.external_id → commands.cmd_id → response; не добавляй retry без понимания результата команды.
- Health-check и запуск актуатора — разные сценарии; при активной lease сохраняй gate и idempotency.
- Результат: участок отказа, доказательства, изменение и реально выполненная точечная проверка.
