# Scheduler Service

Планировщик расписаний зоны (planner-only режим).

## Роль сервиса

`Scheduler` больше не отправляет device-level команды и не выполняет safety/аварийный контроль.

Сервис делает только 2 вещи:
- формирует расписания из `effective-targets` Laravel API;
- отправляет в `automation-engine` **абстрактные задачи** и ждёт статусы `accepted/completed|failed`.
- после рестарта восстанавливает `accepted` задачи из `scheduler_logs` и дофинализирует их через reconcile.

## Поддерживаемые типы задач

- `irrigation` — полив по расписанию
- `lighting` — свет по расписанию
- `ventilation` — проветривание по расписанию
- `solution_change` — смена раствора по расписанию
- `mist` — туман по расписанию
- `diagnostics` — диагностика системы по расписанию

## Контракт

```
Scheduler -> POST /scheduler/bootstrap (automation-engine)
Scheduler -> POST /scheduler/bootstrap/heartbeat (automation-engine)
Scheduler -> POST /scheduler/task (automation-engine, with lease headers)
Scheduler <- GET  /scheduler/task/{task_id} (status polling)
```

Примечания:
- dispatch задач выполняется только после `bootstrap_status=ready`;
- при включенном leader election (`SCHEDULER_LEADER_ELECTION=1`) dispatch выполняет только лидер-инстанс scheduler;
- каждое `POST /scheduler/task` отправляет обязательный `correlation_id` для идемпотентности.
- scheduler пишет lifecycle snapshot `running -> accepted -> completed|failed` в `scheduler_logs`.

## Метрики Prometheus

Порт `9402`:

- `schedule_executions_total{zone_id,task_type}`
- `active_schedules`
- `scheduler_command_rest_errors_total{error_type}`
- `scheduler_diagnostics_total{reason}`
- `scheduler_task_status_total{task_type,status}`
- `scheduler_dispatch_skips_total{reason}`
- `scheduler_leader_role`
- `scheduler_leader_transitions_total{transition}`

## Конфигурация

- `AUTOMATION_ENGINE_URL` (default: `http://automation-engine:9405`)
- `SCHEDULER_TASK_TIMEOUT_SEC` (default: `30`)
- `SCHEDULER_TASK_POLL_INTERVAL_SEC` (default: `1.0`)
- `SCHEDULER_LEADER_ELECTION` (default: `0`)
- `SCHEDULER_LEADER_LOCK_SCOPE` (default: `cluster:default`)
- `SCHEDULER_LEADER_RETRY_BACKOFF_SEC` (default: `2`)
- `SCHEDULER_LEADER_DB_TIMEOUT_SEC` (default: `5`)
- `SCHEDULER_LEADER_HEALTHCHECK_SEC` (default: `10`)
- `SCHEDULER_ACTIVE_TASK_RECOVERY_SCAN_LIMIT` (default: `1000`)

## Тесты

```bash
pytest -q test_main.py
```
