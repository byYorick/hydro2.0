# Scheduler/AETask Chaos Checks

Docker chaos сценарии для проверки отказоустойчивости `scheduler` и `automation-engine` в dev-контуре.

## Скрипты

- `scheduler_leader_failover_chaos.sh`
  - поднимает 2 независимых контейнера scheduler с `SCHEDULER_LEADER_ELECTION=1`;
  - проверяет single-leader состояние;
  - проверяет takeover после остановки лидера.

- `scheduler_restart_recovery_chaos.sh`
  - вставляет `accepted` snapshot scheduler-task в `scheduler_logs`;
  - перезапускает `backend-scheduler-1`;
  - проверяет, что задача финализируется в terminal статус после recovery/reconcile.

- `automation_engine_restart_recovery_chaos.sh`
  - вставляет `running` snapshot `ae_scheduler_task_*` в `scheduler_logs`;
  - перезапускает `backend-automation-engine-1`;
  - проверяет, что startup recovery scanner отдает `failed|task_recovered_after_restart`.

## Запуск

```bash
bash tests/e2e/scheduler/scheduler_leader_failover_chaos.sh
bash tests/e2e/scheduler/scheduler_restart_recovery_chaos.sh
bash tests/e2e/scheduler/automation_engine_restart_recovery_chaos.sh
```
