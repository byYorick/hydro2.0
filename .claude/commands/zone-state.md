---
description: Дамп состояния зоны — workflow phase, последние события, active task, intent
argument-hint: <zone_id>
allowed-tools: Bash(psql:*), Bash(curl:*), Bash(jq:*)
---

Пользователь запросил дамп состояния зоны **$ARGUMENTS**. Если аргумент пустой — попроси указать `zone_id`.

Выполни следующие запросы параллельно (все к `hydro_dev` через локальный `psql`, host=localhost:5432 user=hydro db=hydro_dev) и REST к AE3 (`http://localhost:9405`):

1. **Workflow state** —
   `psql -h localhost -U hydro -d hydro_dev -c "SELECT workflow_phase, payload->>'workflow' AS workflow, updated_at FROM zone_workflow_state WHERE zone_id=$ARGUMENTS"`

2. **Последние 10 zone_events** —
   `psql -h localhost -U hydro -d hydro_dev -c "SELECT type, payload_json::text, created_at FROM zone_events WHERE zone_id=$ARGUMENTS ORDER BY created_at DESC LIMIT 10"`

3. **Active automation intents** —
   `psql -h localhost -U hydro -d hydro_dev -c "SELECT id, intent_type, status, idempotency_key, created_at FROM zone_automation_intents WHERE zone_id=$ARGUMENTS AND status IN ('pending','running') ORDER BY created_at DESC"`

4. **AE3 runtime state** — `curl -s http://localhost:9405/zones/$ARGUMENTS/state | jq .`

5. **Последние 5 команд** —
   `psql -h localhost -U hydro -d hydro_dev -c "SELECT cmd, status, node_uid, channel, created_at FROM commands WHERE zone_id=$ARGUMENTS ORDER BY created_at DESC LIMIT 5"`

Покажи результаты в структурированном виде (секции с заголовками). Если какой-то запрос вернул пусто — отметь это явно. В конце сделай краткое summary: какая фаза, есть ли active task, есть ли stuck intent.

Если БД недоступна (psql error) — подскажи выполнить `make up`.
