# План канонического рефакторинга alerts и AE3 alert lifecycle

**Версия:** 1.3  
**Дата:** 2026-03-29  
**Статус:** Реализован по основному runtime cutover; остались cleanup/doc хвосты

Compatible-With: Protocol 2.0, Backend >=3.0, Python >=3.0, Database >=3.0, Frontend >=3.0.

## Цель

Перевести alert-систему и alert-интеграцию `automation-engine` в одно каноническое состояние без split-brain между:

- Python direct SQL helper-ами;
- AE3 runtime write-path;
- Laravel `AlertService`;
- history-logger retry/DLQ path;
- frontend-настройками поведения alert lifecycle.

Целевой production contract:

`Python/AE3 producer -> Laravel ingest -> AlertService -> alerts + zone_events + realtime`

## Контекст

Исходная проблема была в том, что в кодовой базе одновременно жили несколько несовместимых моделей:

1. legacy Python helper-ы напрямую читают и мутируют `alerts`;
2. AE3 runtime напрямую пишет в `alerts` и `zone_events`;
3. Laravel `AlertService` уже выполняет canonical enrichment/dedup/realtime path;
4. history-logger владеет retry/DLQ transport path для alert delivery;
5. Laravel UI/admin содержал legacy replay path через `pending_alerts.status='dlq'`.

Отсюда следуют реальные дефекты:

- разные write-path дают разные side-effects;
- не все alert mutations попадают в realtime и ledger-consistent `zone_events`;
- `dedupe_key` используется не везде и не является контрактным обязательством;
- resolution semantics разъехались;
- DLQ split между новой и старой моделью;
- в AE3 authority-конфиге есть safety-поля, которые runtime не исполняет.

## Execution Audit 2026-03-29

### Уже реализовано

1. Deliverable A закрыт по коду:
   - backend namespace `system.alert_policies`;
   - enum validation `manual_ack|auto_resolve_on_recovery`;
   - frontend settings card;
   - Laravel policy enforcement в auto-resolve path;
   - tests на API/UI/lifecycle.
2. Основной runtime cutover сделан:
   - введён `AlertPublisher`;
   - `common.alerts`, `common.infra_alerts`, `common.infra_monitor` переведены на canonical producer path;
   - direct SQL lifecycle writes из AE3/runtime code удалены;
   - AE3 business alert emitters переведены на `biz` producer path.
3. DLQ table model унифицирована:
   - Laravel replay path больше не использует `pending_alerts.status='dlq'`;
   - `AlertController`, `ProcessAlert`, `ProcessDLQReplay` работают с `pending_alerts_dlq`.

### Остаточные gap-ы после аудита

1. Replay ownership boundary ещё не доведён до финального канона:
   - таблица уже единая;
   - execution replay всё ещё Laravel-side, а не через отдельный history-logger contract.
2. Документация обновлена частично:
   - core docs обновлены;
   - `API_SPEC_FRONTEND_BACKEND_FULL.md` и `ARCHITECTURE_FLOWS.md` ещё требуют синхронизации под финальный contract.

### Что дополнительно закрыто в версии 1.3

1. `common.error_handler` переведён на `AlertPublisher`; node alerts теперь публикуются через canonical `raise_active` с `dedupe_key`.
2. `PgZoneAlertWriteRepository` удалён полностью; AE3 runtime получает прямую publisher dependency через `BizAlertPublisher`.
3. Regression tests подтверждают новый path:
   - common python alert-path: `25 passed`;
   - AE3 профильный набор: `82 passed`.
4. Добавлен runtime regression guard:
   - `common/test_alert_lifecycle_sql_guard.py`;
   - ловит возврат direct alert SQL mutations и ручных alert zone-event emitters в Python runtime.
5. Guard подключён в GitHub Actions как отдельный check `Alert lifecycle SQL guard`.

## Подтверждённые product decisions

### 1. Политика закрытия AE3 operational alerts

Нужна пользовательская настройка с двумя вариантами:

- `manual_ack`
- `auto_resolve_on_recovery`

### 2. Гранулярность alert identity

Нужна scoped identity, а не только `zone_id + code`.

Следствие:

- `dedupe_key` обязателен для infra alert-ов;
- `dedupe_key` обязателен для node alert-ов;
- `dedupe_key` обязателен для scoped business alert-ов, где один и тот же `code`
  может относиться к разным насосам, каналам, сервисам или узлам.

### 3. Канонический owner lifecycle

Lifecycle alert-а принадлежит Laravel `AlertService`.

Python/AE3/history-logger являются producer-ами и не должны напрямую писать в:

- `alerts`
- `zone_events`

## Неподвижные инварианты

1. Protected command pipeline не меняется:
   `Scheduler -> Automation-Engine -> history-logger -> MQTT -> ESP32`.
2. Прямой MQTT publish из Laravel и AE3 запрещён.
3. Изменения БД делаются только через Laravel migrations.
4. `doc_ai/` остаётся source of truth.
5. Laravel `AlertService` становится единственным writer lifecycle для `alerts`.
6. history-logger остаётся owner transport retry/DLQ для доставки producer payload в Laravel.
7. План не вводит второй alert lifecycle рядом с уже существующим.

## Что документ делает и чего не делает

### Делает

1. Разделяет работу на два deliverable:
   - product-contract + UI policy
   - runtime transport/lifecycle cleanup
2. Фиксирует canonical storage и identity rules.
3. Фиксирует phased DoD.
4. Фиксирует rollout/rollback strategy.

### Не делает

1. Не меняет MQTT contracts.
2. Не меняет protected telemetry pipeline.
3. Не вводит новый storage вне:
   - `alerts`
   - `pending_alerts`
   - `pending_alerts_dlq`
4. Не решает автоматически отдельную safety-задачу по `no_effect` runtime semantics.
   Это отдельный design track.

## Deliverable A. Alert Policy Contract и Frontend Setting

### Scope

В этот deliverable входят только:

1. authority/backend contract для alert policy;
2. frontend control surface;
3. backend semantics чтения policy;
4. docs и tests на policy contract.

### Не входит

1. массовый cutover Python direct-write path;
2. удаление `PgZoneAlertWriteRepository`;
3. DLQ cleanup;
4. вырезание legacy helper-ов.

### Цель deliverable A

Сначала зафиксировать operator-facing semantics и только потом трогать runtime.

Это нужно, чтобы в cutover-фазе не спорить заново, как должен вести себя каждый operational alert.

## Deliverable B. Runtime Lifecycle Cleanup

### Scope

В этот deliverable входят:

1. единый producer contract;
2. Python publisher abstraction;
3. AE3 cutover на canonical path;
4. cleanup legacy SQL writes;
5. DLQ/admin path unification;
6. cleanup guards и integration tests.

### Предусловие

Deliverable B нельзя начинать как production cutover, пока не принят Deliverable A
и не зафиксированы per-code recovery semantics.

## Целевое canonical состояние

### 1. Единый write owner

Единственный lifecycle writer:

- Laravel `AlertService`

Единственные producer operations:

- `raise_active`
- `resolve`

### 2. Единая identity model

Канонический identity contract:

- базовые ключи: `source`, `code`, `zone_id`;
- если alert scoped, обязателен `dedupe_key`;
- scoped identity не должна теряться при retry/replay.

### 3. Единый zone event contract

События:

- `ALERT_CREATED`
- `ALERT_UPDATED`
- `ALERT_RESOLVED`

создаются только Laravel-side contract-ом и только в ledger-consistent payload форме.

### 4. Единый DLQ contract

Transport retry path:

- `pending_alerts`
- `pending_alerts_dlq`

UI/admin path не должен использовать legacy `status='dlq'` в основной таблице как отдельную модель.

## Recovery semantics

Главный недостающий контракт, без которого нельзя безопасно реализовать `auto_resolve_on_recovery`:

- что такое recovery;
- кто его доказывает;
- на каком signal/condition;
- для каких alert code доступно auto-resolve.

### Каноническое правило

Никакой operational alert не получает `auto_resolve_on_recovery`, пока для него не описана
explicit recovery condition.

Если recovery condition не описана:

- policy fallback = `manual_ack`

### Recovery matrix v1

| Alert code | Scope | Recovery доказан когда | Кто закрывает | Допустим `auto_resolve_on_recovery` в v1 |
| --- | --- | --- | --- | --- |
| `biz_ae3_task_failed` | task/zone | не определено единообразно | только manual | нет |
| `biz_clean_fill_timeout` | zone/stage | не определено единообразно | только manual | нет |
| `biz_solution_fill_timeout` | zone/stage | не определено единообразно | только manual | нет |
| `biz_prepare_recirculation_retry_exhausted` | zone/stage | не определено единообразно | только manual | нет |
| `biz_correction_exhausted` | zone/stage | не определено единообразно | только manual | нет |
| `biz_ph_correction_no_effect` | zone/pid_type | не определено единообразно | только manual | нет |
| `biz_ec_correction_no_effect` | zone/pid_type | не определено единообразно | только manual | нет |
| `biz_zone_correction_config_missing` | zone | валидный authority config сохранён и readiness проходит | system | да |
| `biz_zone_dosing_calibration_missing` | zone/component | все required calibration зависимости снова валидны | system | да |
| `biz_zone_pid_config_missing` | zone/pid_type | PID config снова валиден | system | да |
| `biz_zone_recipe_phase_targets_missing` | zone | phase targets снова валидны | system | да |

### Следствие для первой итерации

Frontend setting должна явно показывать, что:

- policy применяется только к alert-ам, где recovery rule формализована;
- остальные alert-ы остаются manual-only даже при global policy `auto_resolve_on_recovery`.

## Storage и индексы

### 1. Где хранится `dedupe_key`

Канонически:

- `details.dedupe_key`

Причина:

- это уже совместимо с текущим Laravel contract;
- не требует немедленного выделения отдельной колонки;
- минимально инвазивно для cutover.

### 2. Ограничения текущей модели

JSON-only хранение `dedupe_key` допустимо только как переходный этап.

Для высокой нагрузки и надёжного `lockForUpdate` path нужен explicit lookup strategy.

### 3. План по индексам

Фаза B1:

- оставить `details.dedupe_key` в JSON;
- добавить индекс/lookup strategy для `details->>'dedupe_key'` в PostgreSQL, если текущая нагрузка покажет это узким местом.

Фаза B2:

- если наблюдаемая нагрузка и explain plans это подтвердят, вынести `dedupe_key`
  в отдельную nullable column `alerts.dedupe_key`;
- синхронизировать её как canonical field и оставить JSON copy только как backward-compatible payload detail.

### 4. Null semantics

Канон:

- `dedupe_key = null` разрешён только для truly non-scoped alert-ов;
- если alert по смыслу scoped, отсутствие `dedupe_key` считается producer defect.

### 5. Legacy records

Старые `ACTIVE` alert-ы без `dedupe_key` не backfill-ятся автоматически в рамках Deliverable A.

Стратегия cutover:

1. новые producer path всегда пишут корректный `dedupe_key`;
2. старые записи остаются как legacy records;
3. lookup logic не должна ломаться на legacy records;
4. optional backfill может быть отдельной задачей только после стабилизации нового path.

## Где хранить policy

### Предлагаемый owner

Первая версия хранится в authority namespace:

- `system.alert_policies`

### Почему это допустимо

Потому что policy влияет на runtime/automation lifecycle semantics, а не только на presentation.

### Ограничение

Документ явно запрещает использовать `system.alert_policies` как свалку для любых ops toggles.

Разрешено только:

- policy, напрямую влияющие на alert lifecycle или automation alert semantics.

Если появятся несвязанные operational toggles, для них нужен отдельный storage decision.

## Точный producer contract

### `raise_active`

Обязательные поля:

- `source`
- `code`
- `type`
- `status='ACTIVE'`
- `zone_id` или явное `null` для global incident
- `details`

Условно-обязательные поля:

- `dedupe_key` для scoped alert-ов
- `node_uid`
- `hardware_id`
- `severity`

### `resolve`

Обязательные поля:

- `code`
- `status='RESOLVED'`
- `zone_id` или `null`
- `details.dedupe_key`, если resolve относится к scoped incident

### Retry/DLQ invariant

Retry и replay не должны менять:

- `code`
- `zone_id`
- `source`
- `dedupe_key`
- scoped metadata

## Фазы реализации

### Фаза A1. Docs и contract hardening

**Цель:** описать канон до изменений в коде.

Сделать:

1. Обновить:
   - `doc_ai/06_DOMAIN_ZONES_RECIPES/EVENTS_AND_ALERTS_ENGINE.md`
   - `doc_ai/04_BACKEND_CORE/PYTHON_SERVICES_ARCH.md`
   - `doc_ai/04_BACKEND_CORE/API_SPEC_FRONTEND_BACKEND_FULL.md`
   - `doc_ai/05_DATA_AND_STORAGE/DATA_MODEL_REFERENCE.md`
   - `doc_ai/ARCHITECTURE_FLOWS.md`
2. Зафиксировать:
   - producer contract
   - identity contract
   - resolve contract
   - recovery matrix
   - DLQ ownership boundary

**DoD A1**

1. В docs нет альтернативного write-owner wording.
2. Recovery matrix определена хотя бы для v1 code set.
3. Явно описано, к каким code policy применяется, а к каким нет.

**Execution status 2026-03-29:** частично закрыто.

Сделано:
- обновлены `EVENTS_AND_ALERTS_ENGINE.md`, `PYTHON_SERVICES_ARCH.md`, `DATA_MODEL_REFERENCE.md`.

Осталось:
- синхронизировать `API_SPEC_FRONTEND_BACKEND_FULL.md`;
- синхронизировать `ARCHITECTURE_FLOWS.md`.

### Фаза A2. Backend policy contract

**Цель:** сделать backend owner для настройки policy.

Сделать:

1. Добавить namespace `system.alert_policies`.
2. Добавить enum validation:
   - `manual_ack`
   - `auto_resolve_on_recovery`
3. Добавить read/write API через unified automation config path.
4. Добавить backend tests для save/load/validation.

**DoD A2**

1. Policy можно сохранить и прочитать через canonical automation API.
2. Invalid enum reject-ится fail-closed.
3. Docs и tests обновлены.

**Execution status 2026-03-29:** закрыто.

### Фаза A3. Frontend setting

**Цель:** дать оператору control surface, но без ложного обещания.

Сделать:

1. Добавить settings UI.
2. Показать два варианта:
   - `Только ручное подтверждение`
   - `Автозакрытие после recovery`
3. Явно показать дисклеймер:
   - применяется только к alert code с описанным recovery contract.

**DoD A3**

1. UI сохраняет policy через canonical API.
2. UI не создаёт впечатление, что все AE3 alerts auto-resolve instantly.
3. Browser/feature tests покрывают сохранение и отображение.

**Execution status 2026-03-29:** закрыто.

### Фаза B1. Python publisher abstraction

**Цель:** подготовить единый runtime path.

Сделать:

1. Ввести `AlertPublisher`.
2. Сконцентрировать в нём:
   - `raise_active`
   - `resolve`
   - dedupe enforcement
3. Перевести на него:
   - `common.infra_alerts`
   - `common.infra_monitor`
   - `common.error_handler`
   - `common.alerts`

**DoD B1**

1. Новый producer path работает без direct SQL writes.
2. `infra_monitor` при recovery вызывает canonical resolve path.
3. Scoped alert-ы получают `dedupe_key`.

**Execution status 2026-03-29:** закрыто.

Сделано:
- `AlertPublisher` введён;
- `common.alerts`, `common.infra_alerts`, `common.infra_monitor` переведены;
- recovery path в `infra_monitor` теперь canonical;
- `common.error_handler` переведён на `AlertPublisher`;
- добавлен профильный тест `common/test_error_handler.py`.

### Фаза B2. AE3 cutover

**Цель:** убрать split-brain внутри `automation-engine`.

Сделать:

1. Перевести все AE3 alert emitters на `AlertPublisher`.
2. Удалить `PgZoneAlertWriteRepository`.
3. Не добавлять новую AE3-side SQL semantics для alerts.
4. Явно не трогать `no_effect` safety policy, кроме одного из вариантов:
   - либо реализовать отдельно по отдельному decision doc;
   - либо удалить ложные config flags из contract.

**DoD B2**

1. В AE3 не осталось direct SQL writes в `alerts`/`zone_events`.
2. AE3 alert-ы создаются через тот же producer contract, что и остальной Python.
3. AE3 tests и integration tests проходят на новом path.

**Execution status 2026-03-29:** закрыто.

Сделано:
- direct SQL writes убраны;
- AE3 business emitters переведены на canonical producer path;
- compatibility adapter `PgZoneAlertWriteRepository` удалён;
- runtime wired на прямой `BizAlertPublisher`;
- профильные AE3 tests зелёные.

### Фаза B3. DLQ/admin path unification

**Цель:** оставить в системе одну модель replay.

Сделать:

1. Выбрать canonical admin boundary:
   - Laravel only displays and triggers replay через history-logger contract;
   - history-logger остаётся настоящим owner replay execution.
2. Удалить legacy path через `pending_alerts.status='dlq'`.
3. Переписать admin UI/controller/command path под `pending_alerts_dlq`.

**DoD B3**

1. В системе один replay contract.
2. Нет legacy path, завязанного на `pending_alerts.status='dlq'`.
3. Replay integration tests проходят.

**Execution status 2026-03-29:** частично закрыто.

Сделано:
- legacy `status='dlq'` path удалён;
- replay переведён на `pending_alerts_dlq`;
- feature test на replay добавлен.

Осталось:
- финально зафиксировать ownership boundary replay execution:
  либо history-logger API/CLI owner,
  либо Laravel façade над ним.

### Фаза B4. Cleanup guards и final cleanup

**Цель:** не допустить возврата легаси.

Сделать:

1. Добавить cleanup guard на Python direct-write path.
2. Добавить grep/CI guard на:
   - `UPDATE alerts`
   - `INSERT INTO alerts`
   - прямые alert lifecycle inserts в `zone_events`
   в Python runtime code, кроме допустимых migration/test fixtures и общего helper `create_zone_event`.
3. Удалить мёртвые helper-ы и устаревшие тесты.

**DoD B4**

1. CI ловит возврат direct SQL lifecycle paths.
2. Не осталось production runtime code с ручной mutation alert tables.

**Execution status 2026-03-29:** закрыто.

Сделано:
- добавлен regression guard `common/test_alert_lifecycle_sql_guard.py`;
- guard ловит прямые SQL lifecycle mutations в `alerts`;
- guard ловит ручные alert event emissions вне Laravel `AlertService`.
- guard подключён в GitHub Actions как отдельный CI step/check;
- cleanup compatibility-слоёв по alert lifecycle завершён в runtime code.

## Rollout и rollback

### Rollout

1. Сначала docs.
2. Затем backend policy contract.
3. Затем frontend UI.
4. Затем новый Python publisher behind feature flag.
5. Затем cutover отдельных producer-ов.
6. Затем AE3 cutover.
7. Только потом DLQ/admin cleanup и удаление legacy.

### Rollback

Rollback допускается только по runtime deliverable B и не должен затрагивать уже сохранённые policy documents.

При rollback:

1. frontend policy UI может остаться read-only;
2. backend policy contract остаётся, но runtime может временно игнорировать его;
3. rollback producer path делается feature flag-ом;
4. dual-write запрещён как постоянный режим;
5. если временный dual-write нужен для migration window, он должен быть bounded по времени
   и документирован отдельно.

## Предлагаемый порядок работ

1. Закрыть Deliverable A целиком.
2. После этого отдельно открыть Deliverable B.

Почему именно так:

- сначала фиксируется продуктовая и operator-facing семантика;
- потом меняется runtime;
- так не появится UI-настройка, которую runtime не уважает.

## Минимальный implementation slice

Первая практическая итерация:

1. docs update;
2. `system.alert_policies`;
3. backend enum validation;
4. frontend setting с дисклеймером;
5. tests для save/load/effective policy.

Это намеренно не включает runtime cleanup.

## Затронутые области

### Документация

- `doc_ai/06_DOMAIN_ZONES_RECIPES/EVENTS_AND_ALERTS_ENGINE.md`
- `doc_ai/04_BACKEND_CORE/PYTHON_SERVICES_ARCH.md`
- `doc_ai/04_BACKEND_CORE/API_SPEC_FRONTEND_BACKEND_FULL.md`
- `doc_ai/05_DATA_AND_STORAGE/DATA_MODEL_REFERENCE.md`
- `doc_ai/ARCHITECTURE_FLOWS.md`

### Laravel

- unified automation config endpoints/services
- `AlertService`
- `PythonIngestController`
- admin/DLQ path
- tests для policy, lifecycle и replay

### Python / services

- `common.alerts`
- `common.infra_alerts`
- `common.infra_monitor`
- `common.error_handler`
- safety/water helper-ы
- AE3 runtime alert emission

### Frontend

- settings screen для `system.alert_policies`
- validation
- explanatory UX

## Критерий завершения

Работа считается полностью завершённой, когда выполнены оба deliverable.

### Done для Deliverable A

1. Policy сохранена в canonical backend contract.
2. Frontend имеет два варианта настройки.
3. Recovery matrix описана и отражена в UI copy.

### Done для Deliverable B

1. В Python/AE3 нет direct SQL lifecycle writes в `alerts` и `zone_events`.
2. Все producer path идут через canonical producer contract.
3. В системе один DLQ/replay contract.
4. Cleanup guards защищают от возврата legacy path.
5. Cross-service integration tests подтверждают консистентность:
   - `alerts`
   - `zone_events`
   - realtime
   - resolve semantics

## Следующие конкретные шаги

1. Досинхронизировать `API_SPEC_FRONTEND_BACKEND_FULL.md` и `ARCHITECTURE_FLOWS.md`.
2. Принять окончательное решение по replay ownership boundary и добить B3 до полного закрытия.
