# План зачистки legacy в automation-подсистеме

**Версия:** 1.0
**Дата:** 2026-04-17
**Автор:** инженерный план, executor-first
**Статус:** draft — требует ack пользователя перед исполнением

Compatible-With: Protocol 2.0, Backend >=3.0, Python >=3.0, Database >=3.0, Frontend >=3.0.

---

## 0. Исходные данные

Baseline-аудит (2026-04-17) после merge `ae3/8bbca59`. Текущий зелёный прогон:
- AE (`make test-ae`): **1276 passed**
- Laravel Feature: **597 passed (3257 assertions)**
- Vitest UI: **1266 passed + 1 skipped** (146 файлов)

См. связанные документы:
- [AE3_CONFIG_REFACTORING_PLAN.md](AE3_CONFIG_REFACTORING_PLAN.md) — план Phase 0–7 (v3.6), **устарел в части Phase 4** (см. Phase 7 ниже)
- [AGENT.md](../../backend/services/automation-engine/AGENT.md) — canonical AE3 contract
- [AUTOMATION_CONFIG_AUTHORITY.md](AUTOMATION_CONFIG_AUTHORITY.md) — authority для config pipeline

---

## 1. Цели

1. **Убрать dead-code** из AE3 `config/` и связанных public API — упростить surface.
2. **Убрать legacy compat-слой в Laravel** (namespace mapping, serialization helpers), если production не использует.
3. **Зачистить residual `.get(key, default)`** в handlers, оставшиеся после Phase 3 migration — обеспечить fail-closed контракт.
4. **Упростить 52 dual-path shim** в `runtime_plan_builder.py` через one-time миграцию БД.
5. **Устранить drift** между `ZoneCorrectionConfigCatalog.php` и `schemas/zone_correction.v1.json` — зафиксировать единый source of truth.
6. **Сохранить намеренно** `_DictShim` (Phase 4 scope, отдельный долгосрочный план) и `compat_endpoints.py`/legacy commands (граничные контракты).
7. **Актуализировать AE3_CONFIG_REFACTORING_PLAN.md** — статус Phase 4 с "deferred" на "completed".

### 1.1 Anti-goals

- ❌ Не затрагивать `_DictShim` mixin и его 22 клиента — это scope Phase 4 плана AE3_CONFIG_REFACTORING_PLAN (оценка 2–4 сессии), в этот план не включается.
- ❌ Не менять `compat_endpoints.py` (граница Laravel→AE3 ingress, толерантность обязательна).
- ❌ Не трогать `update_from_legacy*` / `resolve_legacy_command_id` в `ae_command_repository` — инвариант AGENT.md (обратная совместимость с `commands` таблицей history-logger).
- ❌ Не менять Pydantic-модели в `schema/*.py` без одновременного обновления `schemas/*.v1.json` (Phase 5 авторитет).

---

## 2. Executable runbook

Каждая фаза = отдельный PR, мерджится независимо. Между фазами — прогон `make test-ae` + PHP feature.

### Phase 1 — Dead code removal (0.5 дня, 1 PR, low-risk)

**Цель:** удалить не используемый в production API `load_recipe_phase` + `RecipePhase` экспорт.

**Контекст:** написан в Phase 2 (audit fix B4) как подготовка для hot-reload recipe в `live_reload.py`. После удаления `live_reload.py` (2026-04-17 audit follow-up) функция стала dead. Сейчас её вызывает только [test_ae3lite_recipe_phase_loader.py](../../backend/services/automation-engine/test_ae3lite_recipe_phase_loader.py) (11 тестов, которые не проверяют интеграцию).

**Actions:**
1. Удалить функцию `load_recipe_phase` + импорт `RecipePhase` в [loader.py:22,63-92](../../backend/services/automation-engine/ae3lite/config/loader.py#L22).
2. Удалить экспорты в [config/__init__.py:16,30](../../backend/services/automation-engine/ae3lite/config/__init__.py#L16) и [config/schema/__init__.py:9](../../backend/services/automation-engine/ae3lite/config/schema/__init__.py#L9).
3. Удалить файл-модель [schema/recipe_phase.py](../../backend/services/automation-engine/ae3lite/config/schema/recipe_phase.py) целиком, если не нужен.
4. Удалить `schemas/recipe_phase.v1.json` **ТОЛЬКО** если frontend его не использует — проверить [backend/laravel/resources/js/schemas/](../../backend/laravel/resources/js/schemas/) и imports. Если использует — оставить JSON и удалить только Python-часть.
5. Удалить [test_ae3lite_recipe_phase_loader.py](../../backend/services/automation-engine/test_ae3lite_recipe_phase_loader.py).
6. Обновить audit-документ [AE3_CONFIG_REFACTORING_AUDIT_PHASE_0_2.md](AE3_CONFIG_REFACTORING_AUDIT_PHASE_0_2.md) — пометить B4 closed-as-reverted.

**DoD:**
- `grep -rn "load_recipe_phase\|RecipePhase" backend/services/automation-engine/ae3lite/` → пусто
- `make test-ae` зелёный (ожидается 1265 passed — минус 11 удалённых тестов)

**Rollback:** revert PR. Риск: 0 — мёртвый код.

**Риски:** если `RecipePhase` / `recipe_phase.v1.json` используется где-то во frontend schemas (проверить в действии 4) — оставить JSON Schema и удалить только Python-часть.

---

### Phase 2 — Laravel legacy namespace mapping (1 день, 1 PR, low-risk)

**Цель:** проверить и удалить неиспользуемые legacy-helpers в `AutomationConfigController`.

**Контекст:** [AutomationConfigController.php:361-363,623-628](../../backend/laravel/app/Http/Controllers/AutomationConfigController.php#L361) содержит `serializeLegacySystemDocument()` и `authorityToLegacySystemNamespace()` для старого формата `quality_score_legacy`. После Phase 1-7 плана AE3_CONFIG_REFACTORING эти хелперы могут быть не вызываемы.

**Actions:**
1. `grep -rn "serializeLegacySystemDocument\|authorityToLegacySystemNamespace" backend/laravel/ --include='*.php' --include='*.vue' --include='*.ts'` — проверить callers.
2. Если callers 0 вне контроллера → удалить оба метода + связанные приватные helper'ы.
3. Если остались callers — задокументировать в [AUTOMATION_CONFIG_AUTHORITY.md](AUTOMATION_CONFIG_AUTHORITY.md) §«Legacy mappings» с указанием кто, почему, когда планируется retirement.
4. Проверить маршруты `/api/automation-configs/*` на наличие `?format=legacy` или аналогичных флагов — если есть, аналогично зафиксировать/удалить.

**DoD:**
- Либо helpers удалены и Laravel PHPUnit зелёный, либо явная запись в AUTHORITY-документе.

**Rollback:** revert PR; Laravel зависимостей в БД нет.

**Риски:** могут быть старые seeded конфиги с `quality_score_legacy` payload. Проверить `automation_config_documents.payload` на наличие.

---

### Phase 3 — Residual `.get()` audit в correction.py (1-2 дня, 1 PR)

**Цель:** пройтись по 15 вхождениям `.get(key, default)` в [correction.py](../../backend/services/automation-engine/ae3lite/application/handlers/correction.py) (2405 строк, biggest handler), классифицировать и исправить pre-Phase-3 residuals.

**Классификация (заранее):**

| Тип | Валидно | Действие |
|-----|---------|----------|
| `(raced_event \|\| {}).get("event_type")` — dict из БД, опциональное поле | ✅ valid | keep |
| `task.workflow.correction.get("corr_step")` — опциональное runtime state | ✅ valid | keep |
| `runtime.get("<required_config_field>", default)` — **legacy** fallback на silent default | ❌ invalid | заменить на strict attribute access + `PlannerConfigurationError` |
| `cfg.get("controllers", {})` — структурный guard, где cfg — raw dict | ⚠️ смешанный | перевести на typed `runtime.correction.controllers` attribute |

**Actions:**
1. Собрать таблицу: для каждого `.get()` — line, ключ, default, контекст.
2. Для каждого — решить по классификации (keep/replace).
3. Replace-кейсы переписать на strict attribute-style через `RuntimePlan` (в большинстве мест у handler'а уже есть `runtime: RuntimePlan` параметр).
4. Добавить unit-тест на fail-closed поведение для каждого замененного места (если не покрыт).

**DoD:**
- `grep -cE "\.get\(.*,\s*[^)]+\)" ae3lite/application/handlers/correction.py` ≤ 5 (только валидные event-dict'ы).
- `make test-ae` зелёный.
- Новые failing-fixture тесты подтверждают fail-closed.

**Rollback:** revert PR.

**Риски:**
- **Средний:** можно незаметно сломать прод, если `.get("field", default)` исторически обрабатывал real-world record без `field`. Митигация: перед замещением проверить `automation_effective_bundles` dev-dump на наличие поля во всех записях.

---

### Phase 4 — Snapshot DB migration + runtime_plan_builder cleanup (2-3 дня, 2 PR)

**Цель:** убрать 52× `isinstance(..., Mapping)` shim в [runtime_plan_builder.py](../../backend/services/automation-engine/ae3lite/config/runtime_plan_builder.py) (1176 строк) через one-time migration старых snapshot-записей.

**Контекст:** shims нужны, потому что:
- `snapshot.diagnostics_execution`, `snapshot.phase_targets`, `snapshot.process_calibrations` приходят как `dict` из БД (`zone_snapshots`, `automation_effective_bundles`, phase_extensions).
- Исторические записи могли не иметь полей, которые сейчас обязательны.

**PR 4.1: БД migration (1 день)**
1. Laravel migration: backfill `automation_effective_bundles.config` для всех активных записей, гарантирующий наличие обязательных секций (`correction`, `process_calibration`, `diagnostics_execution`).
2. Seed/re-seed `phase_extensions.targets.diagnostics.execution.startup.*` для всех `grow_cycle_phases` через `AutomationConfigCompiler::compileGrowCycleBundle()`.
3. Feature test: `test_bundle_backfill_adds_missing_sections`.
4. Dry-run на dev → snapshot diff проверить.

**PR 4.2: handler simplification (1-2 дня)**
1. Удалить `isinstance(..., Mapping)` guard'ы там, где PR 4.1 гарантирует структурную полноту.
2. Сохранить guard'ы там, где snapshot-источник **сам по себе** опциональный (например, `profile_row.get("command_plans")` — может отсутствовать по design).
3. Целевое кол-во `isinstance(Mapping)` в файле: ≤ 15 (было 52).
4. Прогнать full AE integration suite.

**DoD:**
- `grep -c "isinstance(.*, Mapping)" runtime_plan_builder.py` ≤ 15
- `make test-ae` зелёный
- `php artisan zones:validate-configs` на dev DB проходит 100%

**Rollback:** revert PR 4.2 (compiler код остаётся валидным, просто верхний слой раньше времени строгий).

**Риски:**
- **Высокий:** prod zones могут иметь inconsistent bundle/snapshot записи, migration может пропустить edge case. Митигация: PR 4.1 сначала на dev → staging → prod (по-очереди), с feature flag "strict runtime plan builder" для быстрого отката.

---

### Phase 5 — ZoneCorrectionConfigCatalog vs zone_correction.v1.json (2 дня, 1 PR)

**Цель:** устранить drift risk между PHP-defaults catalog и JSON Schema.

**Контекст:** [ZoneCorrectionConfigCatalog.php](../../backend/laravel/app/Services/ZoneCorrectionConfigCatalog.php) определяет defaults + field catalog (UI editor). [schemas/zone_correction.v1.json](../../schemas/zone_correction.v1.json) декларирует shape + bounds (canonical per Phase 1). В двух местах разные bound'ы могут рассинхронизироваться.

**Два варианта:**

**Вариант A (рекомендован): JSON Schema canonical, PHP — generated**
1. Написать генератор `tools/generate_zone_correction_catalog.py`: читает `schemas/zone_correction.v1.json` → создаёт `ZoneCorrectionConfigCatalog::fieldCatalog()` массив.
2. Добавить make-target `make generate-config-catalog` + CI gate `make protocol-check`.
3. Удалить ручные определения из PHP — оставить только generated-секцию между маркерами.

**Вариант B: PHP canonical, JSON Schema — generated**
1. Наоборот: `php artisan schema:generate zone_correction` создаёт JSON Schema.
2. Архитектурно хуже — JSON Schema это cross-language контракт, Python loader уже от неё зависит.

**Actions (вариант A):**
1. Сравнить текущие PHP defaults и JSON Schema — составить diff-таблицу несоответствий.
2. Устранить несоответствия (выровнять на JSON Schema).
3. Реализовать генератор + CI-gate.
4. Мигрировать `ZoneCorrectionConfigCatalog::defaults()` и `fieldCatalog()` на generated code.
5. Обновить [AUTOMATION_CONFIG_AUTHORITY.md](AUTOMATION_CONFIG_AUTHORITY.md) с новым single-source declaration.

**DoD:**
- `make generate-config-catalog && git diff --exit-code` — без изменений.
- PHPUnit + AE зелёные.

**Rollback:** revert PR; PHP возвращается к hand-written catalog.

**Риски:** UI-editor использует fieldCatalog() — проверить что generated структура совпадает с Vue.js consumers.

---

### Phase 6 — Sync AE3_CONFIG_REFACTORING_PLAN.md с реальностью (0.5 дня, docs-only)

**Цель:** актуализировать устаревшие секции плана v3.6.

**Контекст:** план помечает Phase 4 (shim removal) как "deferred", но де-факто merge 8bbca59 физически удалил:
- `ae3lite/domain/services/two_tank_runtime_spec.py` (был 1157 строк)
- `ae3lite/domain/services/topology_registry.py`
- `ae3lite/runtime/config.py` (переименован в `env.py`)

При этом `_DictShim` в zone_correction.py жив — остаётся deferred scope.

**Actions:**
1. В [AE3_CONFIG_REFACTORING_PLAN.md](AE3_CONFIG_REFACTORING_PLAN.md) статус-таблицу Phase 4 обновить с ⏸ на ✅ с заметкой "completed in merge 8bbca59 (2026-04-16)".
2. Из Anti-goals/Rollback удалить упоминания legacy файлов как живых.
3. Перенести `_DictShim` retirement в отдельный Phase (новая Phase 8 или в этот план как Phase 7).
4. Добавить cross-link на данный план.
5. Bump версии до v3.7.

**DoD:**
- План актуален относительно HEAD; cross-link с данным документом.

**Rollback:** revert docs-only.

**Риски:** 0.

---

### Phase 7 — `_DictShim` retirement (long-running, отдельный scope)

**Цель:** заменить `_DictShim` mixin в [zone_correction.py:30-79](../../backend/services/automation-engine/ae3lite/config/schema/zone_correction.py#L30) на чистый Pydantic + миграция 22 subclass-клиентов на attribute-style.

**Это НЕ входит в текущий план** — оценка 2–4 сессий по 4–6 часов. Scope:
- Factory `_test_support_runtime_plan.py` уже готов (упомянуто в коде).
- Нужно переписать consumers в handlers (особенно correction.py, 2405 строк), заменить `cfg["key"]` / `cfg.get("key")` на `cfg.key`.
- Характеризационные тесты **до** рефакторинга (R1 из AE3_CONFIG_REFACTORING_PLAN).

**Решение:** выделить в Phase 7 отдельного плана `AE_DICTSHIM_RETIREMENT_PLAN.md` при готовности взяться. Сейчас — **KEEP** с документированием.

---

## 3. Сводный таймлайн

| Фаза | Длительность | Риск | Зависит |
|------|-------------|------|---------|
| 1: Dead code `load_recipe_phase` | 0.5 дня | none | — |
| 2: Laravel legacy mapping | 1 день | low | — |
| 3: `.get()` audit correction.py | 1-2 дня | medium | — |
| 4.1: Snapshot DB backfill migration | 1 день | medium | — |
| 4.2: Handler simplification | 1-2 дня | medium | 4.1 |
| 5: Catalog ↔ JSON Schema sync | 2 дня | low | — |
| 6: Plan v3.7 doc sync | 0.5 дня | none | — |
| 7: `_DictShim` retirement | отдельный plan | high | всё выше |

**Итого этот план (без Phase 7):** ~7-9 дней при одном исполнителе.

---

## 4. Risk register

| # | Риск | Вероятность | Импакт | Митигация |
|---|------|-------------|--------|-----------|
| R1 | `load_recipe_phase` используется в скрытой точке (plugin/cron) | низкая | delete breaks | grep по всему монорепо, dry-run на dev |
| R2 | Prod `automation_effective_bundles` содержат записи, не совпадающие с backfill ожиданиями (Phase 4.1) | средняя | migration failure | dry-run + диагностический `zones:validate-configs --json` до миграции |
| R3 | Correction.py `.get()` замена ломает handler race-handling | средняя | runtime error | характеризационные тесты до рефакторинга, canary deploy |
| R4 | Generated PHP catalog (Phase 5) несовместим с Vue editor | средняя | UI breaks | Vitest контрактный тест fieldCatalog → Vue props |
| R5 | Параллельные правки в ae3 branch от другого разработчика (как было с merge 8bbca59) | средняя | merge conflicts | мёрджить Phase 1-6 последовательно, не откладывать |

---

## 5. Executor-specific

1. **Prod DB миграции (Phase 4.1) НЕ исполняю автоматически** — только dev/staging, для prod сгенерирую SQL и передам пользователю.
2. **Удаление файлов** — каждый `git rm` подтверждаю в тексте ответа (blast radius).
3. **Docker-контейнеры** остаются `make up`; между фазами `make test-ae` + `php artisan test`.
4. **Не менять `composer.json` / `requirements.txt`** без запроса (Phase 1-6 не требует).
5. **Phase 5 генератор** кладу в `tools/` (как existing `generate_authority.py`), не в `backend/`.

**Stop-and-ask points:**
- Phase 1 action 4: если `schemas/recipe_phase.v1.json` используется где-то не в удаляемых местах — stop.
- Phase 3: если `.get()` классификация даёт >5 "invalid" без понятной замены — stop.
- Phase 4.1: перед production-миграцией.
- Phase 5: при обнаружении drift'а в 10+ полях (значит catalog и schema разошлись сильно — нужен архитектурный ревью).

---

## 6. Success metrics (после завершения Phase 1-6)

| Метрика | Команда | Цель |
|---------|---------|------|
| Dead `load_recipe_phase` | `grep -rn "load_recipe_phase" ae3lite/` | 0 |
| Legacy PHP mappers | `grep -rn "serializeLegacySystemDocument\|authorityToLegacySystemNamespace" backend/laravel/` | 0 или документировано |
| `.get()` в correction.py | `grep -cE "\.get\(.*," backend/services/automation-engine/ae3lite/application/handlers/correction.py` | ≤ 5 |
| `isinstance(Mapping)` в runtime_plan_builder | `grep -c "isinstance(.*, Mapping)" runtime_plan_builder.py` | ≤ 15 |
| PHP catalog = JSON Schema | `make generate-config-catalog && git diff --exit-code` | clean |
| AE3_CONFIG_REFACTORING_PLAN v3.7 | `grep "Phase 4.*completed" AE3_CONFIG_REFACTORING_PLAN.md` | match |
| Все тесты зелёные | `make test-ae && php artisan test && npm run test` | exit 0 |

---

## 7. Rollback strategy

| Фаза | Rollback | Impact |
|------|---------|--------|
| 1 | revert PR | none (dead code) |
| 2 | revert PR | Laravel compat возвращается |
| 3 | revert PR | handler возвращается к permissive `.get()` |
| 4.1 | revert migration + re-seed | возвращаем старую shape |
| 4.2 | revert handler PR | 4.1 остаётся, shim-ы живут дольше |
| 5 | revert PR | ручной catalog возвращается |
| 6 | revert docs | план показывает устаревший статус |

Каждая фаза независимо revert-able.

---

## 8. Связанные документы

- [AE3_CONFIG_REFACTORING_PLAN.md](AE3_CONFIG_REFACTORING_PLAN.md) — базовый план refactoring (v3.6 будет обновлён до v3.7 в Phase 6)
- [AUTOMATION_CONFIG_AUTHORITY.md](AUTOMATION_CONFIG_AUTHORITY.md) — config authority, обновить в Phase 2 и 5
- [AGENT.md](../../backend/services/automation-engine/AGENT.md) — canonical AE3 contract
- [ae3lite.md](ae3lite.md) — runtime документация
- `backend/services/automation-engine/_test_support_runtime_plan.py` — test fixture factory (используется в Phase 3/4 при замене mock'ов)
