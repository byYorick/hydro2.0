# AE3 Irrigation Plan Gaps

**Дата:** 2026-03-30  
**Статус:** in_progress  
**Контекст:** после реализации плана `AE3-полив с decision-controller в существующей системе конфигурирования`

Compatible-With: Protocol 2.0, Backend >=3.0, Python >=3.0, Database >=3.0, Frontend >=3.0

---

## 1. Что уже закрыто

Реализовано:
- отдельный AE3 task/workflow `irrigation_start`;
- decision-controller registry с `task` и `smart_soil_v1`;
- authority-path для `zone.logic_profile`, `system.automation_defaults`, `system.command_templates`;
- internal/public backend endpoints для запуска irrigation workflow;
- backward-compatible bridge `FORCE_IRRIGATION -> AE3 start-irrigation`;
- explicit runtime columns в `ae_tasks`;
- schema-safe fallback в Laravel read-model, если миграция `ae_tasks.irrigation_*` ещё не применена;
- UI action для обычного полива через `POST /api/zones/{id}/start-irrigation`;
- разделение operator actions на `normal` и `force` в zone overview;
- проброс irrigation decision metadata в runtime state и execution read-model;
- базовые backend/python/php tests;
- обновление ключевых canonical specs в `doc_ai`.

---

## 2. Незаполненные пункты плана

### 2.1 Decision/recovery/safety конфиги не выведены в реальные формы редактирования

Фактическое состояние:
- типы, parser и payload уже поддерживают `subsystems.irrigation.decision`, `recovery`, `safety`;
- в Vue UI нет реальных input/select/toggle полей для редактирования этих настроек;
- пользователь не может штатно настроить `smart_soil_v1`, lookback, stale timeout, hysteresis, replay policy и `stop_on_solution_min`.

Признак:
- поиск по `irrigationDecision*`, `stopOnSolutionMin`, `irrigationAutoReplayAfterSetup`, `irrigationMaxSetupReplays`
  в `resources/js/Components` и `resources/js/Pages` не даёт реальных form-controls.

Что нужно сделать:
- добавить controls в редактор irrigation/water section;
- связать их с `WaterFormState`;
- покрыть сохранение/загрузку через authority path;
- отобразить sensible defaults и validation hints.

### 2.2 Frontend/unit tests ещё не полностью синхронизированы с новым contract

Фактическое состояние:
- часть узких тестов уже обновлена;
- остаются старые expectations под legacy two-tank command plan shape.

Явный пример:
- `backend/laravel/resources/js/composables/__tests__/zoneAutomationFormLogic.spec.ts`
  всё ещё ожидает `irrigation_recovery_stop` длиной `3`, тогда как canonical shape теперь `4`.

Что нужно сделать:
- обновить frontend unit tests под:
  - `irrigation_start`
  - `irrigation_stop`
  - `irrigation_recovery_stop=4`
  - новые decision/recovery/safety поля;
- прогнать полный vitest suite, а не только точечные тесты.

### 2.3 Decision metadata ещё не доведены до полного operator rendering

Фактическое состояние:
- backend и state/read-model уже отдают `decision_outcome`, `decision_reason_code`, `decision_degraded`, `decision_strategy`;
- базовый UI path для normal/force irrigation уже подключён;
- но полный operator rendering outcome-состояний везде ещё не доведён.

Что нужно сделать:
- отобразить skipped/degraded outcome в execution detail и timeline без пробелов между страницами;
- проверить scheduler/workspace UI на корректный показ decision metadata;
- добавить явные UI labels для `skip`, `degraded_run`, `fail`.

### 2.4 Dashboard и cycle-center quick actions ещё не переведены на новый normal path

Фактическое состояние:
- zone overview уже умеет `normal` и `force`;
- но быстрые действия в dashboard/cycle-center ещё не подтверждены как полностью переведённые на новый public endpoint;
- остаётся риск, что часть operator shortcuts всё ещё живёт вокруг legacy forced semantics.

Затронутые файлы:
- `backend/laravel/resources/js/composables/useDashboardPage.ts`
- `backend/laravel/resources/js/composables/useCycleCenterActions.ts`

Что нужно сделать:
- выровнять quick actions с тем же `normal`/`force` контрактом;
- убедиться, что основной shortcut использует `POST /api/zones/{id}/start-irrigation`;
- оставить legacy `FORCE_IRRIGATION` только как compatibility path.

---

## 3. Технические долги и риски

### 3.1 Не прогнан полный frontend test suite

Прогнаны только точечные тесты:
- `Wizard.spec.ts`
- `useGrowthCycleWizard.spec.ts`
- `ZoneActionModal.spec.ts`
- `ZoneActionModal.validation.spec.ts`
- `Show.spec.ts`
- `Show.integration.spec.ts`
- `ZoneSchedulerTab.spec.ts`

Не подтверждено:
- что остальные vitest suites зелёные;
- что legacy UI integration tests не ломаются на новой семантике полива;
- что build/typecheck целиком не содержит остаточных несоответствий.

### 3.2 Совместимость до миграции закрыта только на уровне read-model

Сделан защитный fallback в:
- `backend/laravel/app/Services/AutomationScheduler/ExecutionRunReadModel.php`

Это решает падение списка/детали execution до применения миграции, но не отменяет необходимость прогнать:
- Laravel migration `2026_03_30_120000_add_ae3lite_irrigation_runtime.php`;
- smoke-проверку сценариев, которые реально пишут `irrigation_*` поля в `ae_tasks`.

### 3.3 Нет полного e2e/operator подтверждения нового UX-контракта

Не подтвержден end-to-end сценарий:
1. оператор запускает `normal` irrigation;
2. decision-controller возвращает `skip|run|degraded_run`;
3. UI корректно показывает outcome;
4. forced path остаётся отдельно доступным;
5. low-solution/setup replay отражается в UI/state/timeline.

### 3.4 Документация обновлена на уровне canonical specs, но не закрыт слой task-specific runbook

Обновлены:
- `doc_ai/04_BACKEND_CORE/ae3lite.md`
- `doc_ai/04_BACKEND_CORE/REST_API_REFERENCE.md`
- `doc_ai/04_BACKEND_CORE/API_SPEC_FRONTEND_BACKEND_FULL.md`
- `doc_ai/05_DATA_AND_STORAGE/DATA_MODEL_REFERENCE.md`

Не хватает при необходимости:
- отдельного task/runbook-документа для operator UX и expected decision outcomes;
- явной короткой схемы `normal vs force` для фронтенда/операторов.

---

## 4. Рекомендуемый следующий этап

Приоритет 1:
- вывести decision/recovery/safety настройки в форму.

Приоритет 2:
- довести UI rendering skipped/degraded outcome;
- синхронизировать dashboard/cycle-center quick actions с `normal`/`force`;
- синхронизировать оставшиеся frontend tests.

Приоритет 3:
- прогнать полный frontend test suite и, при наличии, e2e/operator сценарии;
- применить migration на средах и сделать smoke-проверку записи `irrigation_*` runtime fields.

---

## 5. Краткий вывод

Backend/runtime часть плана реализована заметно глубже, чем на предыдущей итерации.  
Основной незакрытый объём теперь находится в editor UI для irrigation-конфигов, полном operator rendering decision outcome, quick actions и полном frontend test alignment.
