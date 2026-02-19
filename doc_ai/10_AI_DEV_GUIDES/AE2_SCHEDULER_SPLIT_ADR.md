# AE2 Scheduler Split ADR

**Дата:** 2026-02-19  
**Статус:** ACCEPTED  
**Контекст:** декомпозиция `backend/services/scheduler/main.py` без остановки planner-only режима

Compatible-With: Protocol 2.0, Backend >=3.0, Python >=3.0, Database >=3.0, Frontend >=3.0.

## Решение

Принят phased split scheduler на модульные bounded-context слои:

1. `app/bootstrap_sync.py` — bootstrap + heartbeat lifecycle.
2. `app/leader_election.py` — advisory-lock лидерство.
3. `app/dispatch_service.py` — submit/execute dispatch path.
4. `app/reconcile_service.py` — active-task registry, polling, terminal reconciliation.
5. `app/internal_enqueue_service.py` — internal enqueue recovery.
6. `domain/planning_engine.py` — planning/catchup/window dispatch cycle.
7. `app/runtime_loop.py` — главный runtime loop orchestrator.
8. `app/runtime_state.py` — единая dataclass модель runtime mutable state.
9. `infrastructure/*` — изолированные адаптеры AE client / logs / events / metrics.

`backend/services/scheduler/main.py` сохранен как backward-compatible facade:
- публичные имена и сигнатуры сохранены;
- существующие тесты и call-sites не меняются;
- реализация делегирована в новые модули.

## Причины

1. Уменьшить риск роста монолита и hidden coupling.
2. Зафиксировать явные границы ответственности scheduler.
3. Повысить управляемость синхронизации `scheduler <-> automation-engine`.
4. Сохранить безболезненный rollout без Big Bang переписывания.

## Последствия

Плюсы:
1. Логика разделена по контекстам, проще сопровождать и тестировать.
2. Runtime state централизован и управляется через dataclass.
3. Главный loop стал thin orchestration уровнем.

Минусы:
1. На переходном этапе в `main.py` остаются legacy тела функций (dead path до cleanup-phase).
2. Нужен отдельный cleanup PR для физического удаления legacy implementation blocks.

## Rollback

1. Возможен быстрый rollback на pre-split commit.
2. Контрактные API scheduler/AE не менялись, rollback не требует schema/migration шагов.

## Валидация

1. Docker test gate: `docker compose -f backend/docker-compose.dev.yml run --rm --build scheduler pytest -q test_main.py`.
2. Текущий результат: `61 passed`.
