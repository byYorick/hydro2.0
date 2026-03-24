# AUTOMATION_CONFIG_AUTHORITY_TODO.md
# Что ещё недоделано после cutover на automation authority

**Версия:** 1.0  
**Дата обновления:** 2026-03-24  
**Статус:** Рабочий план cleanup и доводки после основного cutover

Compatible-With: Protocol 2.0, Backend >=3.0, Python >=3.0, Database >=3.0, Frontend >=3.0.
Breaking-change: план предполагает окончательное удаление legacy automation config stack без compatibility layer.

---

## 1. Цель документа

Зафиксировать остаточные хвосты после внедрения новой authority-системы и определить порядок добивки, чтобы:

- удалить весь legacy automation config stack;
- довести документацию и тесты до консистентного состояния;
- исключить скрытые fallback/read-path к старым таблицам и старым endpoint-ам.

---

## 2. Что уже является каноном

- authority tables: `automation_config_documents`, `automation_config_versions`,
  `automation_effective_bundles`, `automation_config_violations`,
  `automation_config_presets`, `automation_config_preset_versions`;
- unified API `/api/automation-configs/*`, `/api/automation-bundles/*`, `/api/automation-presets/*`;
- start-cycle authority path через `cycle.*` documents;
- frontend authority-read для settings, correction, PID, process calibration, greenhouse/zone logic profile;
- readiness и bundle-based runtime validation.

---

## 3. Недоделанное в backend/runtime

### 3.1 Полный cleanup legacy имен и моделей

Нужно пройтись по Laravel и Python и удалить/переименовать то, что уже не является authority, но ещё живёт как код или fixture:

- legacy-named модели и сервисы с именами `ZonePidConfig*`, `ZoneCorrectionConfig*`, `ZoneAutomationLogicProfile*`, `GrowCycleOverride*`;
- relation-методы в моделях, которые ссылаются на старые таблицы как на живые runtime owner;
- сообщения, regex и локализации, где ещё фигурируют `zone_pid_configs`, `zone_correction_configs`, `automation_runtime_overrides`.

### 3.2 Полный DB cleanup

После перевода тестов и fixtures на authority:

- дропнуть legacy automation tables миграциями;
- убрать migration-time backfill код, который больше не нужен новым инсталляциям;
- убедиться, что schema dump и clean install поднимаются уже без legacy automation stack.

### 3.3 AE3 integration tests

Нужно перевести integration/e2e тесты Python automation-engine с legacy inserts на:

- `automation_config_documents`
- `automation_effective_bundles`
- `grow_cycles.settings.bundle_revision`

Запрещённые legacy fixtures в новых тестах:

- `zone_automation_logic_profiles`
- `zone_correction_configs`
- `zone_process_calibrations`
- `zone_pid_configs`
- `grow_cycle_overrides`
- `automation_runtime_overrides`

### 3.4 Cleanup guards

Добавить/усилить CI-проверки:

- grep guard на legacy automation routes/controllers/services;
- grep guard на чтение legacy automation tables в runtime/business path;
- grep guard на `env()` в readiness/runtime logic;
- grep guard на старые frontend composables/API calls.

---

## 4. Недоделанное во фронтенде

### 4.1 Полный аудит authority-only read path

Проверить, что:

- authority payload не приходит через Inertia props;
- локальные `FALLBACK_*` не используются как source of truth;
- все editors и wizards читают/пишут только unified automation API.

### 4.2 Удаление legacy типов и helpers

Нужно удалить:

- старые TS types под legacy endpoints;
- payload builders, которые собирали authority локально;
- устаревшие composable-ы и mocks, которые подменяют page props вместо authority API.

### 4.3 Browser e2e

Сейчас нужны явные e2e-сценарии для authority flow:

- settings -> save -> validate -> bundle refresh;
- zone correction/PID/process calibration -> readiness refresh;
- greenhouse profile -> setup wizard -> zone start;
- preset create/apply/update/delete по correction family.

---

## 5. Недоделанное в тестах

### 5.1 Laravel

- feature tests должны seed-ить authority documents, а не legacy tables;
- tests на удалённые endpoints должны явно подтверждать `404`/route absence;
- tests на grow-cycle start должны проверять порядок:
  `cycle docs -> bundle -> snapshot.bundle_revision -> start`.

### 5.2 Python

- unit/integration tests для `water_flow.py` нужно обновить под новое имя/семантику helper-а;
- AE3 tests должны проверять reload по `bundle_revision`, а не по legacy runtime profile;
- нужен smoke test fail-closed на missing bundle / revision mismatch.

### 5.3 Frontend

- покрыть authority history flow;
- покрыть preset CRUD во всех correction-family editor-ах;
- покрыть отсутствие page-prop authority fallback в migrated flows.

---

## 6. Недоделанное в документации

Ещё требуется полный sync следующих документов:

- `04_BACKEND_CORE/API_SPEC_FRONTEND_BACKEND_FULL.md`
- `06_DOMAIN_ZONES_RECIPES/CORRECTION_CYCLE_SPEC.md`
- `06_DOMAIN_ZONES_RECIPES/EFFECTIVE_TARGETS_SPEC.md`
- `06_DOMAIN_ZONES_RECIPES/RECIPE_ENGINE_FULL.md`
- `01_SYSTEM/LOGIC_ARCH.md`

В этих документах ещё встречаются legacy precedence и legacy table names.

---

## 7. Рекомендуемый порядок добивки

1. Перевести оставшиеся Laravel/Python tests и fixtures на authority tables/bundles.
2. Добавить cleanup grep guards в CI.
3. Дропнуть legacy automation tables миграциями и удалить мёртвые модели/relations/services.
4. Добить browser e2e для authority flow и preset CRUD.
5. Полностью синхронизировать оставшиеся domain/API docs.

---

## 8. Критерий завершения

Работа считается завершённой, когда одновременно выполнены все условия:

- в runtime/business path нет чтения legacy automation tables;
- в кодовой базе нет legacy automation routes/controllers/composables;
- clean install и test fixtures не создают legacy automation stack;
- frontend authority data не зависит от Inertia props;
- source-of-truth docs не содержат legacy precedence как канон.
