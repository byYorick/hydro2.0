# AE3 Irrigation Plan Gaps

**Дата:** 2026-03-30  
**Статус:** open  
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
- базовые backend/python/php tests;
- обновление ключевых canonical specs в `doc_ai`.

---

## 2. Незаполненные пункты плана

### 2.1 UI не переведён на two-action irrigation UX

По плану должны быть две явные пользовательские операции:
- `Полить` -> `mode=normal`
- `Принудительно полить` -> `mode=force`

Фактическое состояние:
- UI по-прежнему живёт вокруг legacy-действия `FORCE_IRRIGATION`;
- normal-path через `POST /api/zones/{id}/start-irrigation` как основная операторская кнопка не внедрён;
- отдельной операторской кнопки для `mode=normal` нет.

Затронутые файлы:
- `backend/laravel/resources/js/Pages/Zones/Show.vue`
- `backend/laravel/resources/js/Pages/Zones/Tabs/ZoneOverviewTab.vue`
- `backend/laravel/resources/js/composables/useZoneShowPage.ts`
- `backend/laravel/resources/js/composables/useDashboardPage.ts`
- `backend/laravel/resources/js/composables/useCycleCenterActions.ts`
- `backend/laravel/resources/js/Components/ZoneActionModal.vue`

Что нужно сделать:
- добавить пользовательский normal irrigation action;
- оставить forced action как отдельную explicit операцию;
- развести label/UX/confirmation для `normal` и `force`;
- перевести operator flows на новый public endpoint, а legacy `FORCE_IRRIGATION` оставить только как compatibility path.

### 2.2 Decision/recovery/safety конфиги не выведены в реальные формы редактирования

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

### 2.3 `/api/zones/{id}/state` и execution read-model не отдают decision metadata

По плану UI должен видеть:
- `decision`
- `reason_code`
- `degraded`
- `skip`

Фактическое состояние:
- runtime state уже умеет показывать irrigation phases/stages;
- decision runtime columns в `ae_tasks` есть;
- но state/execution responses не пробрасывают эти поля в operator-facing payload.

Затронутые файлы:
- `backend/services/automation-engine/ae3lite/application/use_cases/get_zone_automation_state.py`
- `backend/laravel/app/Services/AutomationScheduler/ExecutionRunReadModel.php`

Что нужно сделать:
- вернуть `irrigation_decision_outcome`, `irrigation_decision_reason_code`, `irrigation_decision_degraded`
  в `/state` и execution detail;
- отобразить skipped/degraded outcome в timeline/detail UI;
- добавить frontend rendering для этих полей.

### 2.4 Frontend/unit tests ещё не полностью синхронизированы с новым contract

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

### 2.5 Полный operator flow под новый public endpoint не завершён

Фактическое состояние:
- backend endpoint `POST /api/zones/{id}/start-irrigation` существует;
- scheduler path на backend уже умеет вызывать irrigation workflow;
- UI/operator layer не использует этот endpoint как canonical primary action.

Что нужно сделать:
- подключить новый endpoint в UI composables;
- развести `normal` и `force` submit path;
- обновить integration tests фронта и zone page interaction tests.

---

## 3. Технические долги и риски

### 3.1 Не прогнан полный frontend test suite

Прогнаны только точечные тесты:
- `Wizard.spec.ts`
- `useGrowthCycleWizard.spec.ts`

Не подтверждено:
- что остальные vitest suites зелёные;
- что legacy UI integration tests не ломаются на новой семантике полива;
- что build/typecheck целиком не содержит остаточных несоответствий.

### 3.2 Нет полного e2e/operator подтверждения нового UX-контракта

Не подтвержден end-to-end сценарий:
1. оператор запускает `normal` irrigation;
2. decision-controller возвращает `skip|run|degraded_run`;
3. UI корректно показывает outcome;
4. forced path остаётся отдельно доступным;
5. low-solution/setup replay отражается в UI/state/timeline.

### 3.3 Документация обновлена на уровне canonical specs, но не закрыт слой task-specific runbook

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
- внедрить в UI две отдельные irrigation actions: `normal` и `force`;
- подключить public endpoint `POST /api/zones/{id}/start-irrigation` как основной operator path;
- вывести decision/recovery/safety настройки в форму.

Приоритет 2:
- пробросить decision metadata в `/state` и execution detail;
- обновить UI rendering skipped/degraded outcome;
- синхронизировать оставшиеся frontend tests.

Приоритет 3:
- прогнать полный frontend test suite и, при наличии, e2e/operator сценарии.

---

## 5. Краткий вывод

Backend/runtime часть плана в основном реализована.  
Основной незакрытый объём теперь находится в operator UI, frontend contract rendering и полном frontend test alignment.
