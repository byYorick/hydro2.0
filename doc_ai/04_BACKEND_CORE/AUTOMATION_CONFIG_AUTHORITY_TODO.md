# AUTOMATION_CONFIG_AUTHORITY_TODO.md
# Что ещё недоделано после cutover на automation authority

**Версия:** 1.1  
**Дата обновления:** 2026-03-24  
**Статус:** Source-of-truth docs синхронизированы; открытым остаётся только финальный browser smoke в рабочем окружении

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

## 3. Статус backend/runtime

### 3.1 Полный cleanup legacy имен и моделей

Статус: выполнено.

Сделано:

- удалены legacy-named runtime owner модели и сервисы;
- вычищены relation/runtime path на старые automation config tables;
- authority path закреплён в Laravel и Python runtime/tests.

### 3.2 Полный DB cleanup

Статус: выполнено.

Сделано:

- legacy automation tables дропнуты миграциями;
- clean install и authority schema tests идут без legacy automation stack;
- start-cycle authority defaults/materialization работают без старых таблиц.

### 3.3 AE3 integration tests

Статус: выполнено.

Сделано:

- integration/unit tests переведены на `automation_config_documents`, `automation_effective_bundles`, `grow_cycles.settings.bundle_revision`;
- закрыты сценарии correction hot-reload и fail-closed для authority bundle path;
- `water_flow.py` обновлён и покрыт под новую семантику helper-а.

### 3.4 Cleanup guards

Статус: выполнено.

Сделано:

- добавлен CI cleanup guard на legacy automation routes/classes/tables/frontend runtime path;
- guard закреплён в workflow и проверяет authority-only cleanup regression.

---

## 4. Статус во фронтенде

### 4.1 Полный аудит authority-only read path

Статус: выполнено.

Закрыто:

- authority payload не приходит через Inertia props;
- `/settings`, `SystemSettings`, correction/PID/process calibration flows читают и пишут только unified automation API;
- wizard/readiness refresh завязан на authority save path.

### 4.2 Удаление legacy типов и helpers

Статус: выполнено.

Закрыто:

- удалены legacy composables/types/helpers для authority-migrated flows;
- tests и runtime path больше не используют page-props fallback.

### 4.3 Browser e2e

Статус: по коду выполнено, по окружению нужен финальный smoke.

Сделано:

- добавлены browser specs для settings, correction authority flows и setup wizard greenhouse/zone flow;
- suite собирается и листится корректно.

Осталось:

- прогнать full Playwright smoke в корректно поднятом web/auth окружении.

---

## 5. Статус тестов

### 5.1 Laravel

Статус: выполнено.

Закрыто:

- feature tests seed-ят authority documents;
- route absence/removed endpoint tests закреплены;
- grow-cycle start проверяет цепочку `cycle docs -> bundle -> snapshot.bundle_revision -> start`.

### 5.2 Python

Статус: выполнено.

Закрыто:

- unit/integration tests обновлены под authority semantics;
- reload/fail-closed path закреплён через bundle-based tests.

### 5.3 Frontend

Статус: выполнено для migrated authority flows.

Закрыто:

- authority history flow покрыт;
- preset CRUD покрыт для correction family;
- отсутствие page-prop fallback покрыто для migrated pages/flows.

---

## 6. Статус документации

Статус: выполнено на 2026-03-24.

Синхронизированы source-of-truth документы:

- `04_BACKEND_CORE/API_SPEC_FRONTEND_BACKEND_FULL.md`
- `04_BACKEND_CORE/PYTHON_SERVICES_ARCH.md`
- `04_BACKEND_CORE/REST_API_REFERENCE.md`
- `06_DOMAIN_ZONES_RECIPES/CORRECTION_CYCLE_SPEC.md`
- `06_DOMAIN_ZONES_RECIPES/EFFECTIVE_TARGETS_SPEC.md`
- `06_DOMAIN_ZONES_RECIPES/RECIPE_ENGINE_FULL.md`
- `01_SYSTEM/LOGIC_ARCH.md`
- `ARCHITECTURE_FLOWS.md`

Зафиксировано как канон:

- runtime automation-engine (`AE3`) читает compiled authority bundles и operational facts через direct SQL read-model;
- frontend/system settings/correction/PID/process calibration используют unified `/api/automation-configs/*` API;
- `effective-targets` остаются Laravel business/read-model семантикой и diagnostics/integration contract, но не runtime read-path для automation-engine.

---

## 7. Рекомендуемый порядок добивки

1. Прогнать финальный browser smoke в рабочем web/auth окружении.
2. При новых runtime/API изменениях сразу обновлять authority docs, а не копить хвосты.

---

## 8. Критерий завершения

Работа считается завершённой, когда одновременно выполнены все условия:

- в runtime/business path нет чтения legacy automation tables;
- в кодовой базе нет legacy automation routes/controllers/composables;
- clean install и test fixtures не создают legacy automation stack;
- frontend authority data не зависит от Inertia props;
- source-of-truth docs не содержат legacy precedence и legacy runtime wording как канон;
- browser smoke подтверждает authority flow в живом окружении.
