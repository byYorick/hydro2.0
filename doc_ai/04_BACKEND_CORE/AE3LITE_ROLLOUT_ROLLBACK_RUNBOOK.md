# AE3-Lite Rollout And Rollback Runbook

**Версия:** 1.0  
**Дата:** 2026-03-06  
**Статус:** Source of truth для ручного rollout/rollback AE3-Lite `v1`

Compatible-With: Protocol 2.0, Backend >=3.0, Python >=3.0, Database >=3.0, Frontend >=3.0.

## Цель

Зафиксировать воспроизводимую процедуру ручного переключения зоны между `ae2` и `ae3`
без двойного исполнения и без ручного destructive cleanup.

## Контекст

- `AE3-Lite v1` не использует auto-rollout controller.
- Cutover делается только вручную через `zones.automation_runtime`.
- Protected command pipeline остаётся неизменным:
  `Scheduler -> Automation-Engine -> history-logger -> MQTT -> ESP32`.
- Laravel запрещает смену `automation_runtime`, если зона busy:
  - active `ae_tasks`
  - active `ae_zone_leases`
  - indeterminate `ae_commands` state

## Preconditions

Перед любым переключением зоны оператор обязан проверить:

1. Зона выбрана как pilot/candidate и не участвует в параллельных экспериментах.
2. Для зоны нет active `ae_tasks` со статусами `pending|claimed|running|waiting_command`.
3. Для зоны нет active `ae_zone_leases` с `leased_until > now()`.
4. Для зоны нет `ae_commands` с `publish_status in ('pending','accepted')` и `terminal_status IS NULL`.
5. Есть доступ к логам `automation-engine`, `history-logger` и PostgreSQL.

## Pre-check SQL

```sql
SELECT id, status, claimed_by, claimed_at, updated_at
FROM ae_tasks
WHERE zone_id = :zone_id
  AND status IN ('pending', 'claimed', 'running', 'waiting_command')
ORDER BY updated_at DESC, id DESC;

SELECT zone_id, owner, leased_until, updated_at
FROM ae_zone_leases
WHERE zone_id = :zone_id
  AND leased_until > NOW();

SELECT c.id, c.task_id, c.step_no, c.publish_status, c.terminal_status, c.external_id
FROM ae_commands c
JOIN ae_tasks t ON t.id = c.task_id
WHERE t.zone_id = :zone_id
  AND c.publish_status IN ('pending', 'accepted')
  AND c.terminal_status IS NULL
ORDER BY c.updated_at DESC, c.id DESC;
```

Если любой из запросов вернул строки, rollout/rollback запрещён до расследования.

## Rollout: `ae2 -> ae3`

1. Выполнить pre-check SQL.
2. Обновить зону через Laravel API:

```http
PATCH /api/zones/{zone_id}
{
  "automation_runtime": "ae3"
}
```

3. Убедиться, что ответ `200 OK` и `data.automation_runtime = "ae3"`.
4. Перезапустить `automation-engine`.
5. Дождаться завершения startup recovery без ошибок.
6. Выполнить smoke:
   - `POST /zones/{id}/start-cycle`
   - `GET /internal/tasks/{task_id}`
   - появление строки в `ae_commands`
   - terminal reconcile в `ae_tasks.status`

## Rollback: `ae3 -> ae2`

1. Выполнить pre-check SQL.
2. Если есть active AE3 execution state, rollback запрещён до controlled stop / расследования.
3. Обновить зону через Laravel API:

```http
PATCH /api/zones/{zone_id}
{
  "automation_runtime": "ae2"
}
```

4. Убедиться, что ответ `200 OK` и `data.automation_runtime = "ae2"`.
5. Перезапустить `automation-engine`.
6. Сохранить `ae_tasks` и `ae_commands` в БД для расследования; ручной destructive cleanup запрещён.

## Expected denial response

Если зона busy, Laravel возвращает:

```json
{
  "status": "error",
  "code": "runtime_switch_denied_zone_busy",
  "message": "Cannot switch automation runtime while zone is busy.",
  "details": {
    "zone_id": 12,
    "blocker": "active_task|active_lease|indeterminate_command_state"
  }
}
```

## Incident notes

- `active_task`: дождаться terminal state или выполнить controlled stop по отдельной процедуре.
- `active_lease`: дождаться expiry/release и перепроверить pre-check.
- `indeterminate_command_state`: переключение запрещено до расследования command outcome.

## Acceptance

Runbook считается применимым, если:

1. Busy zone не даёт сменить `automation_runtime`.
2. Idle zone переключается через обычный `PATCH /api/zones/{zone}`.
3. После rollout smoke проходит через canonical AE3 paths:
   - `POST /zones/{id}/start-cycle`
   - `GET /internal/tasks/{task_id}`
