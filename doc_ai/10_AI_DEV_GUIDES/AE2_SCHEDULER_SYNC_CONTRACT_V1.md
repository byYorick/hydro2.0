# AE2 Scheduler Sync Contract v1

**Дата:** 2026-02-19  
**Статус:** ACTIVE  
**Версия контракта:** `scheduler-sync/v1`

Compatible-With: Protocol 2.0, Backend >=3.0, Python >=3.0, Database >=3.0, Frontend >=3.0.

## 1. Scope

Контракт описывает синхронизацию между scheduler и automation-engine для abstract-task orchestration.

## 2. Ownership

1. `scheduler` владеет planning/dispatch abstract задач.
2. `automation-engine` владеет исполнением workflow и side-effect publish.
3. Публикация MQTT остается через `history-logger`.

## 3. Required headers

Для `POST /scheduler/task` и `GET /scheduler/task/{task_id}`:
1. `Authorization: Bearer <token>`
2. `X-Trace-Id`
3. `X-Scheduler-Id`
4. `X-Scheduler-Lease-Id` (обязателен в ready bootstrap режиме)

## 4. Required payload fields (`POST /scheduler/task`)

1. `zone_id`
2. `task_type`
3. `payload`
4. `correlation_id`
5. `scheduled_for`

Опционально (deadline windows):
1. `due_at`
2. `expires_at`

## 5. Status model

Terminal set:
1. `completed`
2. `failed`
3. `rejected`
4. `expired`
5. `timeout`

Non-terminal set:
1. `accepted`
2. `running`

## 6. Idempotency semantics

1. `correlation_id` должен быть deterministic для одной logical-задачи.
2. Повторный submit с тем же `correlation_id` не должен создавать новый side-effect execution.
3. Scheduler обязан сохранять `correlation_id + schedule_key + accepted_at` в `scheduler_logs`.

## 7. Lease/heartbeat safety

1. Dispatch допустим только при `bootstrap_status=ready`.
2. Потеря lease/heartbeat переводит scheduler в dispatch-pause.
3. Возврат dispatch — только после подтвержденного ready heartbeat.

## 8. Reconciliation expectations

1. Scheduler поддерживает active-task registry для `accepted/running`.
2. Terminal snapshot по `task_id` пишется единожды.
3. После рестарта scheduler восстанавливает active-task set и завершает их через status polling.
