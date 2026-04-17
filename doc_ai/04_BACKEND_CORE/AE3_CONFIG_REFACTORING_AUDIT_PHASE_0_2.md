# Аудит фаз 0–2 рефакторинга AE3 config

**Дата:** 2026-04-15
**Аудитор:** self-review исполнителя
**Статус:** исторический audit snapshot на 2026-04-15: найдено 2 CRITICAL, 5 MAJOR, 5 MINOR; часть findings позже закрыта в последующих фазах плана, но сам документ сохраняется как audit trail того состояния.

---

## TL;DR

| Область | Зелёное | Красное |
|---|---|---|
| Phase 0 inventory | покрытие 19 namespaces, 48+ полей `zone.correction`, 8 weird behaviors задокументированы | — |
| Phase 1 schemas | 7 schemas valid, 4/4 feature tests, pre-flight artisan работает | **bind mount только в dev compose**; CI workflow не вызывает schemas-validate |
| Phase 2 Pydantic + shadow | 1150 unit-тестов green на момент audit snapshot, метрика live в Prometheus | **drift Pydantic ↔ JSON Schema (Percent)**; нет тестов на shadow hook |

**Что критично исправить ДО Phase 3:**
1. C-1 — `Percent` drift в Pydantic (validation теряет boundary).
2. C-2 — bind mount `../schemas:/schemas:ro` отсутствует в `docker-compose.{ci,prod,dev.win}.yml` и `tests/e2e/docker-compose.e2e.yml`.

Остальное — технический долг, который надо явно зарегистрировать в плане до Phase 7 (observability + AUTHORITY.md gen решает 3 из 5 MAJOR).

---

## 1. CRITICAL findings

### C-1. Pydantic ↔ JSON Schema drift на boundary типа `Percent`

**Где:** [zone_correction.py:24](backend/services/automation-engine/ae3lite/config/schema/zone_correction.py#L24) vs [zone_correction.v1.json:130-133](schemas/zone_correction.v1.json)

**Что:**
| Источник | Bound для `tolerance.prepare_tolerance.{ph_pct, ec_pct}` |
|---|---|
| JSON Schema | `"minimum": 0.1` (inclusive) → принимает `[0.1, 100.0]` |
| Pydantic `Percent` | `Field(gt=0.0, le=100.0)` → принимает `(0.0, 100.0]` |

**Impact:** значение `0.05` Pydantic accepts, JSON Schema rejects. Реальный bug в shadow validation: AE3 Pydantic пропустит payload, который PHP-сторона отвергнет, и `ae3_shadow_config_validation_total{result="ok"}` будет инкрементироваться ложно.

**Fix:** одна строка в [zone_correction.py:24](backend/services/automation-engine/ae3lite/config/schema/zone_correction.py#L24):
```python
Percent = Annotated[float, Field(ge=0.1, le=100.0)]
```

**Severity:** CRITICAL — нарушает declared invariant "Pydantic mirror" Phase 2.

### C-2. Bind mount `schemas/` отсутствует во всех compose-файлах кроме dev

**Где:**
- ✓ [docker-compose.dev.yml:181](backend/docker-compose.dev.yml) — `../schemas:/schemas:ro`
- ✗ `docker-compose.ci.yml:88` — нет
- ✗ `docker-compose.prod.yml` — нет
- ✗ `docker-compose.dev.win.yml:137` — нет
- ✗ `tests/e2e/docker-compose.e2e.yml` — нет

**Impact:**
- В CI workflow `php artisan zones:validate-configs` упадёт на `Schema file missing: /schemas/...`
- Production deploy не сможет выполнять pre-flight check
- Windows-разработчики получат тот же error
- E2E тесты не смогут валидировать config

`JsonSchemaValidator::defaultSchemasRoot()` имеет fallback на `base_path('../../schemas')`, но **только если** `/schemas` директория не существует И env-override не задан. В прод-контейнере путь `base_path('../../schemas')` указывает на `/var/www/../../schemas` — пусто.

**Severity:** CRITICAL — Phase 1 acceptance criterion "make schemas-validate в CI" реально не gate.

**Fix:** добавить mount в 4 compose-файла + повторить ENV `AUTOMATION_SCHEMAS_ROOT` для прод.

---

## 2. MAJOR findings

### M-1. CI workflow protocol-check.yml не вызывает make schemas-validate

**Где:** [.github/workflows/protocol-check.yml](.github/workflows/protocol-check.yml)

**Что:**
- Workflow paths-trigger покрывает `backend/services/common/schemas/**`, `firmware/schemas/**` — но НЕ project-root `schemas/`
- Steps вызывают `tools/check_runtime_schema_parity.sh`, `bash run_contract_tests.sh`, pytest — но `make schemas-validate` или `make protocol-check` не вызываются
- Я добавил dependency `protocol-check: schemas-validate` в Makefile, но CI его не использует

**Impact:** PR с broken JSON Schema (например, JSON syntax error) пройдёт CI зелёным.

**Fix:**
```yaml
on:
  push:
    paths:
      - 'schemas/**'              # add
      - 'tools/validate_schemas.py'  # add
      - 'backend/services/common/schemas/**'
      ...
jobs:
  protocol-check:
    steps:
      - run: pip install 'jsonschema>=4.23'
      - run: python3 tools/validate_schemas.py schemas
      ...
```

**Severity:** MAJOR — нет enforcement, локально gate работает.

### M-2. Нет тестов для `_shadow_validate_correction`

**Где:** [cycle_start_planner.py:208-269](backend/services/automation-engine/ae3lite/domain/services/cycle_start_planner.py#L208)

**Что:** добавил 60-строчный метод с 4 ветвями (mapping check, target collection, validation loop, metric increment). **Ни одна не покрыта тестами.**

**Impact:** регрессия в этом методе не будет поймана. Особенно опасно: если поломаю metric labels — Prometheus alerts будут показывать неправильные данные.

**Fix:** добавить ~5 тестов в `test_ae3lite_cycle_start_planner.py` с monkey-patched `SHADOW_CONFIG_VALIDATION` counter:
1. `correction_config is None` → инкремент `result=invalid`
2. `correction_config = {}` (нет base/phases) → `result=invalid`
3. Все 4 payload (base + 3 phases) валидны → `result=ok`
4. Один phase invalid → `result=invalid`, log WARNING
5. ConfigValidationError carries zone_id

**Severity:** MAJOR — code path в production без test coverage.

### M-3. Нет автоматической проверки drift Python ↔ JSON Schema

**Что:** Pydantic мин/макс заданы вручную, дублируют JSON Schema. Любое изменение в одном — silent drift.

C-1 нашёл уже одно расхождение. Без CI gate новые drift'ы будут добавляться.

**Fix (один из):**
- A) `datamodel-code-generator` в Phase 7 + commit generated файл; CI: regenerate + diff
- B) Тест-парсер: `tests/test_pydantic_jsonschema_parity.py` — извлекает constraints из обеих сторон, сравнивает
- C) Сгенерировать JSON Schema из Pydantic (`model.model_json_schema()`) и diff с canonical файлом

Выбор: **B** — самый простой для Phase 3 (один тест-файл, нет codegen pipeline).

**Severity:** MAJOR — гарантированный technical debt.

### M-4. Pydantic для `recipe.phase` не создан, хотя critical для Q4

**Что:** Q4 (live mode покрывает recipe phase) требует hot-reload `RecipePhase`. В Phase 2 я создал `schemas/recipe_phase.v1.json`, но Pydantic для него — нет.

В Phase 5 я планирую `load_effective_recipe_phase()`, но **без модели RecipePhase это невозможно**. Phase 5 заблокирована скрытым deferred.

**Fix:** добавить `ae3lite/config/schema/recipe_phase.py` в начало Phase 3 (или конец Phase 2 в виде +1 task).

**Severity:** MAJOR — скрытый блокер Phase 5.

### M-5. Phase 2 completion summary занизил scope

**Что:** в моём ответе после Phase 2 написал "57 unit-тестов зелёные". Реально я прогнал ТОЛЬКО `test_ae3lite_config_loader.py + test_ae3lite_two_tank_runtime_spec.py + test_ae3lite_cycle_start_planner.py`. Полный suite из 1150 тестов прогнан только сейчас (в аудите) — он зелёный, но это retroactive validation.

**Impact:** ввёл пользователя в заблуждение о scope DoD-проверки. Plan говорил "make test-ae green" — формально я этого требования не выполнял до сейчас.

**Fix:** retroactive — `make test-ae` сейчас зелёный (1150 passed). Записать в plan changelog как Phase 2 acceptance retroactively confirmed 2026-04-15.

**Severity:** MAJOR — процессное нарушение, не impact на код.

---

## 3. MINOR findings

### m-1. `ec_dosing_mode` добавлен только в `defaults()`, но не в `fieldCatalog()`

**Где:** [ZoneCorrectionConfigCatalog.php](backend/laravel/app/Services/ZoneCorrectionConfigCatalog.php)

`defaults()` (lines 84-91) теперь содержит `ec_dosing_mode`, но `fieldCatalog()` (lines 115-289) — UI-метаданные для editor — не обновлён. Frontend editor для zone.correction не покажет это поле.

**Impact:** оператор не сможет редактировать через UI до Phase 6. Для Phase 3-5 не критично.

**Severity:** MINOR — будет fix в Phase 6.

### m-2. Нет .env.example записи для `AUTOMATION_SCHEMAS_ROOT`

**Где:** `backend/laravel/.env.example`

Env-переменная объявлена в `JsonSchemaValidator::defaultSchemasRoot()`, но нигде не задокументирована.

**Impact:** новый разработчик не узнает о ней без чтения PHP кода.

**Severity:** MINOR — документация.

### m-3. Shadow validation вызывается ТОЛЬКО для two_tank topology

**Где:** [cycle_start_planner.py:129](backend/services/automation-engine/ae3lite/domain/services/cycle_start_planner.py#L129) — внутри `_build_two_tank_plan()`

**Что:** для lighting_tick plan (`_build_lighting_tick_plan`) shadow не вызывается. На текущий момент AE3 v1 — only two_tank, поэтому это OK, но не задокументировано.

**Impact:** при добавлении новой topology без shadow integration — silent gap.

**Fix:** перенести shadow вызов в `build()` (top of method) либо в `execute_task` use case. Альтернатива — комментарий "// only for two_tank topology".

**Severity:** MINOR — preventive.

### m-4. Shadow логи могут спамить при invalid zones

**Где:** [cycle_start_planner.py:255](backend/services/automation-engine/ae3lite/domain/services/cycle_start_planner.py#L255) — `_logger.warning(...)`

**Что:** каждый `_build_two_tank_plan()` вызов даёт WARNING если payload invalid. На dev стеке уже 1 zone invalid → 1 WARNING на каждый task claim. С `make test-ae` — десятки лишних логов в test output.

**Impact:** шум, но не функциональная проблема.

**Fix:** rate-limit (no more than 1 WARNING per zone per minute) или DEBUG-level вместо WARNING.

**Severity:** MINOR — observability hygiene.

### m-5. JSON Schema `$defs/PhaseOverride` объявлен, но не используется в `zone_correction.v1.json` напрямую

**Где:** [zone_correction.v1.json](schemas/zone_correction.v1.json) `$defs/PhaseOverride`

**Что:** Используется через `$ref` из `zone_correction_document.v1.json:phase_overrides`. Это OK архитектурно (shared $def), но не задокументировано в README.

**Impact:** могу удалить случайно при cleanup.

**Severity:** MINOR — добавить комментарий.

---

## 4. Положительные находки (тоже важно)

| # | Что |
|---|---|
| ✓ 1 | `make test-ae` зелёный — 1150 unit-тестов AE прошли (включая 17 cycle_start_planner и 25 two_tank_runtime_spec) |
| ✓ 2 | Phase 0 inventory обнаружил **3 mismatch** между PHP и Python (`prepare_recirculation_correction_slack_sec`: 0 vs 900 — 15 минут разница!), zafix-ил Phase 1 patch |
| ✓ 3 | Schemas validated по meta-schema 2020-12 (justinrainbow не работал → opis выбран корректно) |
| ✓ 4 | Live данные в Prometheus подтверждают shadow integration в реальном стеке: `ae3_shadow_config_validation_total{result=invalid}=1.0` |
| ✓ 5 | Composer.lock зафиксирован — opis/json-schema 2.x reproducible |
| ✓ 6 | `extra="forbid"` + `frozen=True` на всех Pydantic models — защита от опечаток и runtime mutation |
| ✓ 7 | Feature test ValidateZoneConfigsCommand 4/4 — PHP-side validator работает |
| ✓ 8 | Inventory зафиксировал 6 design decisions (D1-D6) до Phase 3 |

---

## 5. Action plan (gating Phase 3 start)

**Обязательно (CRITICAL fixes):**

| # | Action | Effort | Owner |
|---|---|---|---|
| A1 | Fix Pydantic `Percent` → `Field(ge=0.1, le=100.0)` | 1 min | executor |
| A2 | Add bind mount `../schemas:/schemas:ro` in compose: ci, prod, dev.win, e2e | 10 min | executor |
| A3 | Re-run loader tests + `make test-ae` после A1 | 5 min | executor |

**Рекомендуется (MAJOR fixes до Phase 3 sprint 3.1):**

| # | Action | Effort |
|---|---|---|
| B1 | Add CI workflow paths-trigger `schemas/**` + step `python3 tools/validate_schemas.py schemas` | 15 min |
| B2 | Add 5 tests for `_shadow_validate_correction` in `test_ae3lite_cycle_start_planner.py` | 30 min |
| B3 | Add `tests/test_pydantic_jsonschema_parity.py` — 1 test, parses both, diffs constraints | 1-2h |
| B4 | ~~Create `ae3lite/config/schema/recipe_phase.py` Pydantic + loader function (Q4 prep)~~ **closed-as-reverted** (2026-04-17): `recipe_phase.py`, `load_recipe_phase` и `schemas/recipe_phase.v1.json` удалены — `live_reload.py` был удалён ранее, функция стала dead code, файл тестов `test_ae3lite_recipe_phase_loader.py` удалён вместе с ней. | — |
| B5 | Update plan.md changelog: Phase 2 retroactive `make test-ae` confirmation | 5 min |

**Можно отложить до Phase 7:**

| # | Action |
|---|---|
| C1 | `ZoneCorrectionConfigCatalog::fieldCatalog()` обновить с `ec_dosing_mode` |
| C2 | `.env.example` запись для `AUTOMATION_SCHEMAS_ROOT` |
| C3 | Shadow rate-limiting WARNING логов |
| C4 | Перенос shadow call в base plan builder (для будущих topology) |

---

## 6. Метрики аудита

| Metric | Value |
|---|---|
| Findings всего | 12 (2 CRITICAL + 5 MAJOR + 5 MINOR) |
| Phase 1 critical fixes до Phase 3 | 2 (A1, A2) |
| Phase 2 retroactive issues | 1 (M-5: incomplete Phase 2 DoD) |
| Технический долг переносится в Phase 7 | 4 (B3, C1-C3) |
| Тесты в проекте после Phase 0-2 | 1150 unit (AE) + 4 feature (Laravel) = green |
| Schemas (валидные по meta-schema) | 7/7 |
| Pydantic models созданы | 1 из ~5 запланированных (zone_correction; missing: recipe_phase, zone_pid, zone_process_calibration, zone_logic_profile) |
| Live прод-метрика | `ae3_shadow_config_validation_total` подключена и пишет данные |

---

## 7. Заключение

**Phase 0-2 выполнена корректно по основным критериям**, но имеет 2 CRITICAL bug-а и значительный технический долг.

**Decision matrix для перехода в Phase 3:**

| Сценарий | Действие |
|---|---|
| Хотим стартовать Phase 3 СЕЙЧАС с fix'ом A1+A2 (~15 мин) | OK, Phase 3 sprint 3.1 безопасен |
| Хотим стартовать Phase 3 СЕЙЧАС без fix'ов | НЕ рекомендую — Pydantic drift даст false positive в shadow metric, исказит данные перед Phase 3 переключением |
| Хотим закрыть весь технический долг до Phase 3 | +3-5 часов работы (B1-B5) — рекомендуется если есть время |

**Моя рекомендация:** выполнить A1 + A2 + B5 (минимум), затем стартовать Phase 3.1 (correction.py migration). B1-B4 — параллельно с Phase 3 (могут быть отдельными PR).

**Самооценка процесса:** 7/10. Технически работает, но недостаточная самопроверка scope (Phase 2 DoD заявлен раньше реальной валидации) и пропущенный drift говорят о том, что нужно усилить self-review **до** заявления "phase done".
