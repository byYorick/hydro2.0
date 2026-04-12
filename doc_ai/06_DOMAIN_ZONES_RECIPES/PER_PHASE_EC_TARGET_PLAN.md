# Per-Phase EC Target для двухбакового контура

**Ветка:** `ae3`  
**Статус:** Планирование  
**Дата:** 2026-04-12  
**Совместимость:** Breaking change для AE3 runtime, backward-compatible при отсутствии nutrition ratios

---

## 1. Проблема

### 1.1 Суть бага

В двухбаковой топологии EC target из рецепта (например, 1.5 mS/cm) используется **одинаково** для всех фаз workflow — и для подготовки раствора (solution_fill / tank_recirc), и для полива (irrigation / irrig_recirc).

Однако при подготовке раствора дозируется **только NPK** (single mode), который вкладывает лишь ~44% от общего EC. Система пытается довести EC до полного target = 1.5, используя только NPK → **NPK передозируется в ~2.3 раза**.

При поливе система переключается на Ca/Mg/micro (multi_sequential, NPK excluded), но EC уже = 1.5 от перекосированного NPK → Ca/Mg/micro **не дозируются вообще** (gap = 0).

### 1.2 Корневая причина

`runtime["target_ec"]` — единственное значение для всех фаз, полученное из `_resolve_phase_target()` в `two_tank_runtime_spec.py:172-173`. Никакого масштабирования по активным компонентам не происходит.

### 1.3 Затронутые точки в коде

| Файл | Строка | Использование `runtime["target_ec"]` |
|------|--------|--------------------------------------|
| `ae3lite/application/handlers/correction.py` | 313 | `build_dose_plan()` — расчёт дозы |
| `ae3lite/application/handlers/correction.py` | 358-361 | `is_within_tolerance()` — проверка достижения цели |
| `ae3lite/application/handlers/base.py` | 770 | `_targets_reached()` — проверка готовности |
| `ae3lite/application/handlers/base.py` | 824 | `_workflow_ready_values_match()` — готовность к переходу |

### 1.4 Пример

Рецепт: EC target = 1.5 mS/cm, NPK = 44%, Ca = 36%, Mg = 14%, Micro = 8%.

**Сейчас (неправильно):**

| Фаза | EC target | Что дозируется | Результат |
|------|-----------|---------------|-----------|
| solution_fill | 1.5 | Только NPK | NPK передозирован ×2.3, EC = 1.5 от одного NPK |
| irrigation | 1.5 | Ca/Mg/micro | gap = 0, ничего не дозируется |

**Как должно быть:**

| Фаза | EC target | Что дозируется | Результат |
|------|-----------|---------------|-----------|
| solution_fill | 0.66 (= 1.5 × 0.44) | Только NPK | NPK даёт 0.66, корректно |
| irrigation | 1.50 (полный) | Ca/Mg/micro | gap = 0.84, Ca/Mg/micro дозируются |

---

## 2. Доли EC по компонентам (справочные данные)

### 2.1 Физико-химические основы

EC определяется ионной проводимостью раствора. Каждая соль вносит свой вклад пропорционально молярной проводимости её ионов:

| Ион | λ° (S·cm²/mol) | Основной источник |
|-----|-----------------|-------------------|
| K⁺ | 73.5 | NPK (KNO₃, KH₂PO₄) |
| NO₃⁻ | 71.4 | NPK + Calcium Nitrate |
| Ca²⁺ | 59.5 (½) | Calcium Nitrate |
| Mg²⁺ | 53.1 (½) | MgSO₄ (Epsom Salt) |
| SO₄²⁻ | 80.0 (½) | MgSO₄ |
| H₂PO₄⁻ | 33.0 | NPK (KH₂PO₄) |

### 2.2 Типичные доли по данным исследований

Источники: Hoagland solution, Masterblend 2:2:1, Salt Index, HydroBuddy model.

| Компонент | Доля EC (%) | Обоснование |
|-----------|------------|-------------|
| **NPK** | 40–48% | KNO₃ + KH₂PO₄ — высокая ионная проводимость K⁺/NO₃⁻ |
| **Calcium** | 32–40% | Ca(NO₃)₂ — средне-высокий Salt Index |
| **Magnesium** | 10–15% | MgSO₄ — средняя проводимость |
| **Micro** | 3–8% | Хелаты Fe, Mn, Zn, Cu, B, Mo — минимальный вклад |

### 2.3 Рекомендуемые дефолты для 4-компонентной системы

**Универсальный дефолт:**

```
npk: 42%, calcium: 36%, magnesium: 14%, micro: 8%
```

**По культурам:**

| Культура | EC target (mS/cm) | NPK | Calcium | Magnesium | Micro |
|----------|-------------------|-----|---------|-----------|-------|
| Салат / зелень | 0.8–1.4 | 42% | 38% | 13% | 7% |
| Томаты | 2.0–3.5 | 44% | 35% | 13% | 8% |
| Клубника | 1.0–1.5 | 42% | 36% | 14% | 8% |
| Перцы | 1.5–2.5 | 44% | 35% | 13% | 8% |

### 2.4 Текущие дефолты в проекте

В `recipeEditorShared.ts:createDefaultRecipePhase()`:
```
npk: 44%, calcium: 36%, magnesium: 17%, micro: 3%
```

В `ExtendedRecipesCyclesSeeder.php` (3-компонентная модель):
```
npk: 44%, calcium: 44%, micro: 12%
```

**Рекомендация:** Обновить frontend-дефолты micro: 3% → 8%, magnesium: 17% → 14% для лучшего соответствия физико-химическим данным. Не блокирует основной фикс.

---

## 3. Архитектура решения

### 3.1 Принцип

EC — **кумулятивная** величина: каждый компонент добавляет свою долю к общему EC раствора. Поэтому:

- **Подготовка** (solution_fill / tank_recirc): вода чистая → дозируем NPK → target = `full_ec × npk_share`
- **Полив** (irrigation / irrig_recirc): раствор уже содержит NPK → дозируем Ca/Mg/micro → target = `full_ec` (сенсор видит суммарный EC, gap = то, что нужно добрать Ca/Mg/micro)

### 3.2 Формула

```
npk_share = npk_ratio / sum(all_ratios)     # e.g. 44 / 100 = 0.44

target_ec_prepare   = full_ec × npk_share   # e.g. 1.5 × 0.44 = 0.66
target_ec_irrigation = full_ec               # e.g. 1.5 (кумулятивно)
```

### 3.3 Fallback при отсутствии ratios

Если `ec_component_ratios` не заданы (старые зоны, `dose_ml_l_only` mode, single mode без multi-component) → `npk_share = 1.0` → `target_ec_prepare = full_ec`. Поведение не меняется — **полная backward-совместимость**.

---

## 4. План реализации

### Фаза 1 — AE: per-phase EC target в runtime

**Файл:** `backend/services/automation-engine/ae3lite/domain/services/two_tank_runtime_spec.py`

**Изменения:**

1. Добавить функцию `_compute_prepare_ec_share(correction_cfg)`:
   ```python
   def _compute_prepare_ec_share(solution_fill_cfg: Mapping, base_cfg: Mapping) -> float:
       """Доля EC для фазы подготовки (NPK) от полного target.
       
       Берёт ec_component_ratios из solution_fill или base конфига.
       Если ratios не заданы — возвращает 1.0 (backward compat).
       """
       ratios = (
           _to_mapping(solution_fill_cfg.get("ec_component_ratios"))
           or _to_mapping(base_cfg.get("ec_component_ratios"))
       )
       if not ratios:
           return 1.0
       
       npk = _non_negative_float(ratios.get("npk"), 0.0)
       total = sum(_non_negative_float(v, 0.0) for v in ratios.values())
       
       if total <= 0 or npk <= 0:
           return 1.0
       
       return npk / total
   ```

2. В `resolve_two_tank_runtime()` после строки 173:
   ```python
   target_ec_full = _resolve_phase_target(snapshot=snapshot, zone_id=zone_id, key="ec")
   npk_share = _compute_prepare_ec_share(solution_fill_cfg, resolved_base_cfg)
   target_ec_prepare = round(target_ec_full * npk_share, 4)
   ```

3. В `runtime` dict (строки 259-264) добавить:
   ```python
   "target_ec": target_ec_full,                    # backward compat, полный target
   "target_ec_prepare": target_ec_prepare,          # для solution_fill / tank_recirc
   "target_ec_prepare_min": round(target_ec_min * npk_share, 4),
   "target_ec_prepare_max": round(target_ec_max * npk_share, 4),
   "npk_ec_share": npk_share,                       # для логирования / UI
   ```

---

### Фаза 2 — AE: phase-aware target selection в handlers

**Файл:** `backend/services/automation-engine/ae3lite/application/handlers/base.py`

**Изменения:**

1. Добавить метод `_effective_ec_target()`:
   ```python
   def _effective_ec_target(self, *, task: Any, runtime: Mapping[str, Any]) -> float:
       """EC target с учётом текущей фазы workflow.
       
       solution_fill / tank_recirc → target_ec_prepare (NPK-доля)
       irrigation / irrig_recirc   → target_ec (полный, кумулятивный)
       """
       phase = normalize_phase_key(getattr(task.workflow, "workflow_phase", None))
       if phase in ("solution_fill", "tank_recirc"):
           prepare = runtime.get("target_ec_prepare")
           if prepare is not None:
               return float(prepare)
       return float(runtime["target_ec"])
   ```

2. Аналогично `_effective_ec_min()` и `_effective_ec_max()`.

3. Обновить `_targets_reached()` (строка 770):
   ```python
   ec_target = self._effective_ec_target(task=task, runtime=runtime)
   ```

4. Обновить `_workflow_ready_values_match()` (строка 824):
   ```python
   ec_target = self._effective_ec_target(task=task, runtime=runtime)
   ```

---

### Фаза 3 — AE: correction handler

**Файл:** `backend/services/automation-engine/ae3lite/application/handlers/correction.py`

**Изменения:**

1. `_run_check()` (строка 313):
   ```python
   target_ec = self._effective_ec_target(task=task, runtime=runtime)
   ```

2. Все downstream вызовы `is_within_tolerance()` и `build_dose_plan()` автоматически получат правильный target_ec — они уже используют локальную переменную `target_ec`.

3. Логирование `CORRECTION_COMPLETE` и `CORRECTION_PLANNER_CONFIG_INVALID` (строки 379-384, 438-439) — `target_ec` уже отражает phase-aware значение.

---

### Фаза 4 — AE: тесты

**Новый файл:** `backend/services/automation-engine/tests/test_per_phase_ec_target.py`

**Тест-кейсы:**

1. **`test_prepare_ec_share_basic`** — `_compute_prepare_ec_share({npk: 44, ca: 36, mg: 14, micro: 8})` = 0.44
2. **`test_prepare_ec_share_no_ratios`** — без ratios → 1.0 (backward compat)
3. **`test_prepare_ec_share_npk_zero`** — npk=0 → 1.0 (safety fallback)
4. **`test_runtime_target_ec_prepare`** — `resolve_two_tank_runtime()` возвращает `target_ec_prepare = ec_target × npk_share`
5. **`test_runtime_target_ec_irrigation`** — `target_ec` = полный recipe EC (не масштабирован)
6. **`test_correction_uses_prepare_target_in_solution_fill`** — correction handler в solution_fill_check использует `target_ec_prepare`
7. **`test_correction_uses_full_target_in_irrigation`** — correction handler в irrigation_check использует полный `target_ec`
8. **`test_workflow_ready_uses_prepare_target`** — `_workflow_ready_values_match()` в prepare_recirculation_check использует `target_ec_prepare`

**Обновить существующие тесты:**
- `test_ae3lite_correction_planner_multi_component.py` — в multi_sequential тестах target_ec теперь = full EC (без изменений, т.к. тест уже для irrigation)
- `test_ae3lite_handler_solution_fill.py` — убедиться, что correction entry использует prepare target
- `test_ae3lite_handler_prepare_recirc_check.py` — workflow_ready с prepare target

---

### Фаза 5 — Frontend: EC-breakdown в RecipeEditor

**Файл:** `backend/laravel/resources/js/composables/recipeEditorShared.ts`

**Изменения:**

1. Добавить helper-функцию:
   ```typescript
   export function computeEcBreakdown(phase: RecipePhaseFormState): {
     npk: number; calcium: number; magnesium: number; micro: number; total: number;
   } {
     const ec = phase.ec_target ?? 0;
     const ratios = {
       npk: phase.nutrient_npk_ratio_pct ?? 0,
       calcium: phase.nutrient_calcium_ratio_pct ?? 0,
       magnesium: phase.nutrient_magnesium_ratio_pct ?? 0,
       micro: phase.nutrient_micro_ratio_pct ?? 0,
     };
     const sum = ratios.npk + ratios.calcium + ratios.magnesium + ratios.micro;
     if (sum <= 0 || ec <= 0) {
       return { npk: 0, calcium: 0, magnesium: 0, micro: 0, total: 0 };
     }
     return {
       npk: +(ec * ratios.npk / sum).toFixed(3),
       calcium: +(ec * ratios.calcium / sum).toFixed(3),
       magnesium: +(ec * ratios.magnesium / sum).toFixed(3),
       micro: +(ec * ratios.micro / sum).toFixed(3),
       total: ec,
     };
   }
   ```

**Файл:** `backend/laravel/resources/js/Pages/Recipes/RecipeEditor.vue`

**Изменения:**

1. В секции EC targets, после полей ec_target/min/max, добавить блок EC-breakdown:
   ```vue
   <div v-if="ecBreakdown.total > 0" class="mt-2 text-sm text-gray-500 dark:text-gray-400 space-y-0.5">
     <div class="font-medium text-gray-600 dark:text-gray-300">EC по компонентам:</div>
     <div class="grid grid-cols-2 gap-x-4 gap-y-0.5 pl-2">
       <span>NPK:</span>         <span>{{ ecBreakdown.npk }} mS/cm ({{ phase.nutrient_npk_ratio_pct }}%)</span>
       <span>Calcium:</span>     <span>{{ ecBreakdown.calcium }} mS/cm ({{ phase.nutrient_calcium_ratio_pct }}%)</span>
       <span>Magnesium:</span>   <span>{{ ecBreakdown.magnesium }} mS/cm ({{ phase.nutrient_magnesium_ratio_pct }}%)</span>
       <span>Micro:</span>       <span>{{ ecBreakdown.micro }} mS/cm ({{ phase.nutrient_micro_ratio_pct }}%)</span>
     </div>
     <div class="mt-1 text-xs text-blue-600 dark:text-blue-400">
       Подготовка раствора: EC → {{ ecBreakdown.npk }} (NPK) · 
       Полив: EC → {{ ecBreakdown.total }} (+ Ca/Mg/Micro)
     </div>
   </div>
   ```

2. Computed property:
   ```typescript
   const ecBreakdown = computed(() => computeEcBreakdown(phase))
   ```

---

### Фаза 6 — Backend: усиление валидации

**Файл:** `backend/laravel/app/Http/Controllers/RecipeRevisionPhaseController.php`

**Изменения:**

1. В `validateNutritionRatioSum()` (строки 159-209) — дополнительное правило:
   - Если `nutrient_mode` ∈ {`ratio_ec_pid`, `delta_ec_by_k`} и `ec_target > 0`, то все 4 `nutrient_*_ratio_pct` **обязательны** (не nullable)
   - Это гарантирует, что AE всегда сможет вычислить `npk_share`

**Файл:** `backend/laravel/resources/js/composables/recipeEditorShared.ts`

**Изменения:**

1. В `getRecipePhaseTargetValidationError()` (строки 477-489) — аналогичная frontend-валидация:
   - Если `nutrient_mode` задан и `ec_target > 0` — проверить наличие всех 4 ratios

---

## 5. Порядок выполнения

| # | Фаза | Файлы | Зависимости |
|---|------|-------|-------------|
| 1 | AE: per-phase EC target | `two_tank_runtime_spec.py` | — |
| 2 | AE: phase-aware handlers | `base.py`, `correction.py` | Фаза 1 |
| 3 | AE: тесты | `tests/test_per_phase_ec_target.py` + обновление существующих | Фазы 1-2 |
| 4 | Frontend: EC-breakdown | `recipeEditorShared.ts`, `RecipeEditor.vue` | Независимо |
| 5 | Backend: валидация | `RecipeRevisionPhaseController.php`, `recipeEditorShared.ts` | Независимо |
| 6 | Прогон тестов | pytest AE, npm typecheck/lint | Фазы 1-5 |

**Фазы 4 и 5 могут выполняться параллельно с фазами 1-3.**

---

## 6. Backward compatibility

| Сценарий | Поведение |
|----------|-----------|
| Зона без `ec_component_ratios` | `npk_share = 1.0` → `target_ec_prepare = full_ec` → без изменений |
| `nutrient_mode = dose_ml_l_only` | Ratios не применяются к correction → `npk_share = 1.0` |
| Старые рецепты без magnesium | 3-компонентная модель: npk + calcium + micro → `npk_share` вычисляется корректно |
| `ec_dosing_mode = single` (solution_fill) | NPK single pump — target масштабируется правильно |
| `ec_dosing_mode = multi_sequential` (irrigation) | Ca/Mg/micro — full EC target, gap = full - NPK_contribution |

---

## 7. PID state при смене фазы

При переходе solution_fill → irrigation EC target скачком меняется (0.66 → 1.50). PID integrator **должен** сбрасываться. Проверить:

- `_reset_pid_state_if_inside_bounds()` уже сбрасывает PID при входе в tolerance window
- При transition `prepare → ready → irrigation` создаётся новое correction state → PID state фактически начинается заново
- **Дополнительных изменений не требуется** — текущий механизм сброса PID при смене фазы работает корректно

---

## 8. Связанные документы

- `doc_ai/06_DOMAIN_ZONES_RECIPES/CORRECTION_CYCLE_SPEC.md` — state machine коррекции
- `doc_ai/06_DOMAIN_ZONES_RECIPES/EFFECTIVE_TARGETS_SPEC.md` — резолв targets из рецепта
- `doc_ai/04_BACKEND_CORE/ae3lite.md` — AE3 runtime contract
- `backend/laravel/app/Support/Automation/RecipeNutritionRuntimeConfigResolver.php` — маппинг ratios → correction_config
- `backend/services/automation-engine/ae3lite/domain/services/correction_planner.py` — PID + dose calculation

---

## 9. Критерии приёмки

- [ ] `resolve_two_tank_runtime()` возвращает `target_ec_prepare = ec_target × npk_share`
- [ ] `_effective_ec_target()` возвращает `target_ec_prepare` для solution_fill / tank_recirc
- [ ] `_effective_ec_target()` возвращает полный `target_ec` для irrigation / irrig_recirc
- [ ] `is_within_tolerance()` в correction handler использует phase-aware target
- [ ] `_workflow_ready_values_match()` использует phase-aware target
- [ ] При отсутствии ratios → `npk_share = 1.0` → поведение не меняется
- [ ] Frontend показывает EC-breakdown по компонентам в RecipeEditor
- [ ] Frontend показывает подсказку: подготовка EC vs полив EC
- [ ] Валидация: `ratio_ec_pid` / `delta_ec_by_k` + `ec_target > 0` → 4 ratios обязательны
- [ ] Все существующие тесты AE проходят (`pytest -x -q`)
- [ ] Frontend: `npm run typecheck` и `npm run lint` без ошибок
