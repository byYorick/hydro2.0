# LARAVEL_SCHEDULER_MIGRATION_PLAN_FOR_AI.md
# План завершения миграции scheduler в Laravel для ИИ-ассистентов

**Версия:** v1.2  
**Дата:** 2026-02-20  
**Статус:** LEGACY / SUPERSEDED  
**Область:** `backend/laravel`, `backend/services/automation-engine`, `tests/e2e`, `doc_ai`

Compatible-With: Protocol 2.0, Backend >=3.0, Python >=3.0, Database >=3.0, Frontend >=3.0.
Breaking-change: owner планирования/dispatch перенесен на Laravel scheduler; Python scheduler выведен из runtime compose-профилей.

> Внимание: актуальный контракт scheduler-dispatch описан в
> `doc_ai/04_BACKEND_CORE/ae3lite.md`.
> Разделы с task-transport и polling legacy-статусов в этом документе исторические.

---

## 1. Цель

Завершить миграцию scheduler в Laravel без нарушения защищенного command path:

`Scheduler(Laravel) -> Automation-Engine -> History-Logger -> MQTT -> ESP32`.

`automation-engine` остается execution-plane (workflow/decision/dispatch), Laravel берет на себя planner/control-plane.

---

## 2. Текущее состояние (As-Is, зафиксировано)

## 2.1 Что уже реализовано

1. В Laravel уже есть runtime-команда scheduler dispatch:
   - `backend/laravel/app/Console/Commands/AutomationDispatchSchedules.php` (~1405 LOC).
2. Внутри команды уже реализованы:
   - planning (`buildSchedulesForZone`, `scheduleCrossings`, `applyCatchupPolicy`);
   - dispatch (`dispatchSchedule`);
   - polling/reconcile (`isScheduleBusy`, `fetchTaskStatus`);
   - cursor management (`resolveZoneLastCheck`, `persistZoneCursor`);
   - config/bootstrap (`schedulerConfig`, `bootstrapLease`).
3. Есть feature-flag включения Laravel scheduler:
   - `AUTOMATION_LARAVEL_SCHEDULER_ENABLED` в compose-конфигах.
4. Python `scheduler` выведен из runtime compose-профилей:
   - сервис удален из `backend/docker-compose.dev.yml`,
   - сервис удален из `backend/docker-compose.dev.win.yml`,
   - сервис удален из `backend/docker-compose.prod.yml`.

## 2.2 Что не завершено

1. Код Laravel scheduler остается монолитом (техдолг декомпозиции).
2. Durable state переведен на отдельную модель данных scheduler:
   - активные задачи: `laravel_scheduler_active_tasks` (+ `ActiveTaskStore`);
   - курсоры зон: `laravel_scheduler_zone_cursors` (+ `ZoneCursorStore`);
   - Cache оставлен как ускоритель, source of truth перенесен в БД.
3. Покрытие Laravel scheduler пути добавлено (unit internals + feature dispatch/recovery + CI smoke job).
4. Legacy Python scheduler удален из default runtime compose-профилей и из текущей рабочей ветки.
   Rollback возможен только через отдельный artifact (release tag/compose overlay).

## 2.3 Текущие значения env по compose (важно)

По текущим `docker-compose` defaults:

1. `AUTOMATION_LARAVEL_SCHEDULER_ENABLED=${...:-0}`

Уточнение:
1. `0` в compose-файлах — безопасный шаблонный default (dispatch не активен, пока флаг явно не включен для окружения).
2. Для рабочего окружения dispatcher включается явным `AUTOMATION_LARAVEL_SCHEDULER_ENABLED=1`.
3. Риск dual-dispatch снят, потому что Python scheduler выведен из runtime compose-профилей.
4. Отдельно контролируется риск `no-dispatch` (если флаг оставлен в `0` в окружении, где ожидается активный scheduler).

## 2.4 Статус миграционных вех

**Уже выполнено:**

1. `LRS-026`: shadow режим Laravel scheduler.
2. `LRS-027`: canary переход.
3. `LRS-028`: full rollout Laravel scheduler.
4. Удаление Python scheduler из runtime compose-профилей.
5. `LRS-018..020`: unit/feature/recovery тесты для `automation:dispatch-schedules`.
6. `LRS-022`: CI job `laravel-scheduler-smoke`.

**Осталось сделать:**

1. Рефакторинг монолита Laravel scheduler (`LRS-004..010`).
2. Формализованный rollback artifact и rollback drill.

---

## 3. Явная граница миграции

**Переносим в Laravel:**

1. Валидацию конфигов.
2. Профили логики.
3. UI-oriented read APIs.
4. Audit-агрегации.
5. Операторские команды как intent.

**Не переносим из `automation-engine`:**

1. Workflow orchestration.
2. Decision engine.
3. Retry/backoff/recovery.
4. Dispatch команд.
5. Single-writer arbitration.

---

## 4. Непереговорные инварианты

1. Прямой MQTT publish из Laravel запрещен.
2. `automation-engine` остается owner исполнения workflow и командного side-effect пути.
3. Любые изменения БД только через Laravel migrations.
4. Контракт scheduler-task синхронизируется в `doc_ai/04_BACKEND_CORE/*` до/вместе с кодом.

## 4.1 Семантика статусов (уточнение)

**Business status owner: `automation-engine`**
- `accepted`, `running`, `completed`, `failed`, `rejected`, `expired`.

**Transport status owner: scheduler (Laravel)**
- `timeout`, `not_found`.

**Обязательное поведение Laravel scheduler:**

1. `timeout`:
   - не интерпретировать как business-failed;
   - повторять polling до `expires_at`/policy;
   - после исчерпания окна фиксировать terminal transport `timeout`.
2. `not_found`:
   - делать ограниченные retries с backoff;
   - если задача не появилась в окне reconcile -> terminal transport `not_found` + diagnostics event.
3. Запрещено маппить `timeout|not_found` в business `failed` без явной transport маркировки.

---

## 5. Приоритеты (исправленная модель)

## P0 (блокирует надежность)

1. Durable state scheduler (active tasks + cursors в БД).
2. Проверяемый rollback artifact для legacy scheduler (без ручного редактирования compose).
3. Тесты/recovery/CI для Laravel scheduler path.

## P1 (критичный техдолг)

1. Декомпозиция `AutomationDispatchSchedules` в сервисы.
2. Нормализация observability/timeline parity.

## P2 (сопровождение)

1. Финальная синхронизация документации.
2. Финальная зачистка legacy scheduler ссылок/артефактов после rollback-drill.

Примечание: документация важна, но не блокирует старт P0 по durable state.

---

## 6. Implementation Backlog

### EPIC A (P0): Durable state Laravel scheduler

1. `LRS-011` (DONE): таблица активных задач scheduler (`laravel_scheduler_active_tasks`).
2. `LRS-012` (DONE): таблица курсоров по зонам (`laravel_scheduler_zone_cursors`).
3. `LRS-013` (DONE): `ActiveTaskStore` + `ZoneCursorStore`; reconcile читает durable state, Cache только ускоритель.
4. `LRS-014` (DONE): индексы + retention/cleanup в цикле dispatcher (config-driven batch cleanup).

**Минимальная схема (обязательный baseline):**

```sql
CREATE TABLE laravel_scheduler_active_tasks (
    id BIGSERIAL PRIMARY KEY,
    task_id VARCHAR(128) NOT NULL UNIQUE,
    zone_id BIGINT NOT NULL,
    task_type VARCHAR(64) NOT NULL,
    schedule_key VARCHAR(255) NOT NULL,
    correlation_id VARCHAR(255) NOT NULL,
    status VARCHAR(32) NOT NULL, -- accepted|running|completed|failed|rejected|expired|timeout|not_found
    accepted_at TIMESTAMPTZ NOT NULL,
    due_at TIMESTAMPTZ NULL,
    expires_at TIMESTAMPTZ NULL,
    last_polled_at TIMESTAMPTZ NULL,
    terminal_at TIMESTAMPTZ NULL,
    details JSONB NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_lsat_zone_status ON laravel_scheduler_active_tasks(zone_id, status, updated_at DESC);
CREATE INDEX idx_lsat_schedule_key ON laravel_scheduler_active_tasks(schedule_key, updated_at DESC);
CREATE INDEX idx_lsat_expires_at ON laravel_scheduler_active_tasks(expires_at);

CREATE TABLE laravel_scheduler_zone_cursors (
    zone_id BIGINT PRIMARY KEY,
    cursor_at TIMESTAMPTZ NOT NULL,
    catchup_policy VARCHAR(32) NOT NULL,
    metadata JSONB NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_lszc_cursor_at ON laravel_scheduler_zone_cursors(cursor_at DESC);
```

**Retention baseline:**

1. `active_tasks`: хранить terminal записи 30-90 дней (config-driven), затем cleanup batch job.
2. `zone_cursors`: хранить всегда (только upsert), cleanup не требуется.

**Приемка:**

1. Рестарт Laravel не теряет `accepted/running` задачи.
2. `resolveZoneLastCheck` больше не читает курсор из `scheduler_logs`.
3. Cache остается только как ускоритель, не как source of truth.

### EPIC B (P0): Post-cutover safety и rollback readiness

5. `LRS-026` (DONE): shadow режим Laravel scheduler.
6. `LRS-027` (DONE): canary зоны.
7. `LRS-028` (DONE): full rollout Laravel scheduler.
8. `LRS-031` (P0): добавить rollback artifact для legacy scheduler
   (отдельный compose overlay или задокументированный release tag).
9. `LRS-032` (P0): провести и зафиксировать rollback drill с проверкой отсутствия dual-dispatch.

**Обязательные правила:**

1. В одном окружении в один момент времени только один активный dispatcher owner.
2. Если legacy scheduler включается через rollback artifact, owner dispatch переключается явно и атомарно.
3. Любое нарушение фиксируется как deployment blocker.

**Приемка:**

1. Нет дублей `correlation_id` по двум scheduler источникам.
2. Нет двойного dispatch одного `schedule_key` в окне TTL.

### EPIC C (P0): Тесты и CI

10. `LRS-018` (DONE): unit planning/catchup/correlation/deadlines (`AutomationDispatchSchedulesInternalsTest`).
11. `LRS-019` (DONE): feature тесты `automation:dispatch-schedules` (HTTP fake, durable assertions).
12. `LRS-020` (DONE): recovery тест restart active tasks (reconcile persisted task + next dispatch).
13. `LRS-022` (DONE): CI job `laravel-scheduler-smoke`.

**Приемка:**

1. Есть тесты bootstrap/heartbeat/dispatch/reconcile/recovery.
2. CI fail-fast при регрессии scheduler path.

### EPIC D (P1): Рефакторинг монолита Laravel scheduler (техдолг)

14. `LRS-004` (P1): thin-entrypoint для command.
15. `LRS-005` (P1): `SchedulerConfig`.
16. `LRS-006` (P1): `BootstrapClient`/HTTP adapter.
17. `LRS-008` (P1): `PlanningService`.
18. `LRS-009` (P1): `DispatchService`.
19. `LRS-010` (P1): `ReconcileService`.

**Важно:** это рефакторинг существующей функциональности, а не greenfield разработка.

### EPIC E (P1): Observability/UI parity

20. `LRS-023` (P1): scheduler events в `zone_events`.
21. `LRS-024` (P1): метрики scheduler path.
22. `LRS-025` (P1): UI lifecycle/timeline parity.

### EPIC F (P2): Документация и decommission legacy

23. `LRS-001` (P2): ADR + owner модель.
24. `LRS-002` (P2): sync API docs.
25. `LRS-003` (P2): sync execution schema docs.
26. `LRS-029` (DONE): decommission Python scheduler runtime.
27. `LRS-030` (P2): runbooks/rollback + финальная зачистка docs.

---

## 7. Координация ролей ИИ-ассистентов (исправлено)

1. `AI-ARCH` подготавливает контракт/ADR/task-файлы.
2. `AI-CORE-LARAVEL` делает кодовые изменения только по утвержденным task-файлам.
3. `AI-QA` блокирует merge при незакрытых критериях приемки.
4. `AI-OPS` выполняет только cutover/rollback шаги после PASS от `AI-QA`.

**Workflow:** `AI-ARCH -> AI-CORE-LARAVEL -> AI-QA -> AI-OPS`.

**Разрешение конфликтов:**

1. Источник истины по контракту: `AI-ARCH` + owner репозитория.
2. При расхождении `AI-CORE` и `AI-QA` merge блокируется, решение только через обновленный task-файл и rerun.

---

## 8. Проверка состояния перед rollback

Перед rollback обязательно:

1. Проверить, что в текущем runtime нет legacy scheduler сервиса:
```bash
docker compose -f backend/docker-compose.dev.yml ps | rg scheduler
```
2. Проверить фактические env значения в target окружении:
```bash
docker compose -f backend/docker-compose.dev.yml config | rg "AUTOMATION_LARAVEL_SCHEDULER_ENABLED"
```
3. Для rollback artifact проверить, что в его конфиге присутствует переключатель legacy dispatch:
```bash
docker compose -f backend/docker-compose.dev.yml -f <rollback-overlay>.yml config | rg "SCHEDULER_DISABLE_DISPATCH"
```
4. Проверить наличие rollback artifact (compose overlay или release tag), который реально поднимает legacy scheduler.
5. Проверить runtime логи scheduler dispatch path за один и тот же интервал.
6. Проверить отсутствие dual-dispatch по `correlation_id`/`schedule_key` в `scheduler_logs`.
7. Проверить отсутствие ссылок на legacy scheduler в compose/CI:
```bash
rg -n "scheduler" backend/docker-compose*.yml .github/workflows/ci.yml
```

Без этих проверок rollback считается недействительным.

---

## 9. Rollback стратегия (проверяемая)

1. Зафиксировать current snapshot env и статус dispatcher owner.
2. Выключить Laravel scheduler:
   - `AUTOMATION_LARAVEL_SCHEDULER_ENABLED=0`.
3. Поднять rollback artifact из предыдущего release tag (до decommission), если требуется возврат к legacy scheduler.
4. Для legacy scheduler dispatch-настройки применять только внутри rollback artifact (в текущей ветке не используются).
5. Перезапустить только затронутые сервисы.
6. Прогнать smoke:
   - bootstrap OK;
   - dispatch проходит;
   - polling/reconcile возвращает terminal outcomes;
   - нет dual-dispatch.
7. Зафиксировать rollback event в `scheduler_logs` и runbook.

---

## 10. Оценки времени (недекоративные)

Оценки ниже даны диапазонами и требуют уточнения после `LRS-011` (durable state baseline):

1. EPIC A (durable state): 3-6 дней.
2. EPIC B (cutover safety): 2-4 дня.
3. EPIC C (tests/CI): 2-4 дня.
4. EPIC D (refactor debt): 4-8 дней.
5. EPIC E (observability/UI parity): 1-3 дня.
6. EPIC F (docs + decommission): 1-3 дня.

---

## 11. Definition of Done

1. Laravel scheduler является единственным planner/dispatch owner в runtime.
2. `automation-engine` остается единственным execution owner.
3. Python scheduler не выполняет dispatch в production и не присутствует в default runtime compose-профилях.
4. Durable state реализован в БД, restart-safe.
5. Есть проверенный rollback artifact и успешный rollback drill.
6. Контракт, тесты, CI и runbooks синхронизированы.
