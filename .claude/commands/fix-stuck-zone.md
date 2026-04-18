---
description: Разблокировать застрявшую зону (DELETE zone_workflow_state + ack alerts) — с подтверждением
argument-hint: <zone_id>
allowed-tools: Bash(psql:*), Bash(curl:*), Bash(jq:*)
---

Пользователь хочет разблокировать зону **$ARGUMENTS**. Если аргумент пустой — попроси указать `zone_id`.

## Шаг 1 — Диагностика (до любых DELETE)

Выполни параллельно и покажи результат:

1. Текущий workflow_phase:
   `psql -h localhost -U hydro -d hydro_dev -c "SELECT workflow_phase, payload->>'workflow', updated_at FROM zone_workflow_state WHERE zone_id=$ARGUMENTS"`

2. Active tasks:
   `psql -h localhost -U hydro -d hydro_dev -c "SELECT id, status, zone_id FROM zone_automation_tasks WHERE zone_id=$ARGUMENTS AND status IN ('pending','claimed','running','waiting_command')"`

3. Active lease:
   `psql -h localhost -U hydro -d hydro_dev -c "SELECT * FROM zone_leases WHERE zone_id=$ARGUMENTS"`

4. Unacked alerts:
   `psql -h localhost -U hydro -d hydro_dev -c "SELECT id, type, severity, created_at FROM alerts WHERE zone_id=$ARGUMENTS AND acknowledged_at IS NULL ORDER BY created_at DESC LIMIT 10"`

## Шаг 2 — Анализ и подтверждение

**ОБЯЗАТЕЛЬНО:** прежде чем что-то удалять — покажи пользователю что нашёл и **спроси подтверждение**. Destructive-операции требуют явного согласия.

Если есть **active task в статусе `claimed/running/waiting_command`** — предупреди: удаление workflow_state при активной task может привести к неконсистентности. Предложи сначала дождаться завершения или вручную пометить task как `failed`.

## Шаг 3 — Разблокировка (только после подтверждения)

Если пользователь подтвердил:

1. `psql -h localhost -U hydro -d hydro_dev -c "DELETE FROM zone_workflow_state WHERE zone_id=$ARGUMENTS"` — сбросит stuck workflow (irrig_recirc lock и т.д.)

2. Ack всех unacked алертов через API (если есть):
   - Сначала залогиниться: `TOKEN=$(curl -s -X POST http://localhost:8080/api/auth/login -H 'Content-Type: application/json' -d '{"email":"admin@example.com","password":"password"}' | jq -r .token)`
   - `curl -X PATCH http://localhost:8080/api/alerts/{id}/ack -H "Authorization: Bearer $TOKEN"` для каждого id

## Шаг 4 — Верификация

Повтори шаг 1 — убедись что `zone_workflow_state` пусто и `alerts` уменьшилось. Покажи итог.
