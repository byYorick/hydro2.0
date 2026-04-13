# RECIPE_ENGINE_FULL.md
# Полная архитектура Recipe Engine 2.0

Recipe Engine — это подсистема, которая управляет рецептами выращивания:
версиями рецептов, фазами с целями по колонкам, циклами выращивания и effective targets.

Инварианты модели:

- нет `zone_recipe_instances` + JSON targets как source of truth;
- версионирование через `RecipeRevision`, активный цикл — `GrowCycle`;
- цели фаз — по колонкам и authority bundles; `targets` в API может быть derived view;
- канонический write-contract фазы: flat columns + `extensions.day_night` + `extensions.subsystems.irrigation.targets.system_type`;
- атомарное создание растения/цикла/ревизии на backend, не оркестрация цепочки только на фронте.


Compatible-With: Protocol 2.0, Backend >=3.0, Python >=3.0, Database >=3.0, Frontend >=3.0.
Breaking-change: обратная совместимость со старыми форматами и алиасами не поддерживается.

Актуализация (2026-04-13):
- В `recipe_revision_phases` / `grow_cycle_phases` добавлены flat-поля `irrigation_system_type`, `substrate_type`, `day_night_enabled`, `nutrient_ec_dosing_mode` (см. §2.1.1).
- Появилась справочная таблица `substrates` и CRUD endpoints `/api/substrates` (см. §2.4).
- Snapshot immutability и роль `GrowCyclePhase` как единственного runtime-источника зафиксированы в §3.5.
- Уточнена семантика `changeRecipeRevision('now' | 'next_phase')` и инвариант пересчёта compiled bundle при смене фазы (§3.3).
- Добавлен endpoint `GET /api/recipes/{recipe}/active-usage` для предупреждения UI о редактировании используемого рецепта (§4.1).

---

## 1. Назначение Recipe Engine

Recipe Engine отвечает за:

- хранение и версионирование рецептов;
- хранение фаз (этапов роста);
- определение целей (targets) для каждой фазы;
- управление переходами между фазами;
- предоставление контроллерам зон информации о текущих целях.

---

## 2. Новая модель данных (после рефакторинга)

**Иерархия сущностей:**
1. `Recipe` — базовый рецепт для растения/культуры
2. `RecipeRevision` — версия рецепта (DRAFT/PUBLISHED/ARCHIVED)
3. `RecipeRevisionPhase` — шаблон фазы с целями по колонкам
4. `RecipeRevisionPhaseStep` — шаги внутри фазы
5. `GrowCycle` — активный цикл выращивания (центр истины)
6. `GrowCyclePhase` — снапшот фазы для конкретного цикла
7. `GrowCyclePhaseStep` — снапшот шагов для цикла
8. `GrowCycleOverride` — перекрытия параметров
9. `GrowCycleTransition` — история переходов

**Ключевой принцип:** Рецепты версионируются, активный цикл использует зафиксированную ревизию.

### 2.1. Канонический контракт `RecipeRevisionPhase`

Primary write-shape:

- flat поля таблицы `recipe_revision_phases`;
- `extensions.day_night`;
- `extensions.subsystems.irrigation.targets.system_type`.

Read-shape для API/Inertia:

- те же flat поля;
- `extensions` как есть;
- derived `targets` для UI/read-model совместимости.

`extensions.day_target/night_target` больше не записываются. Если такие данные встречаются в старых строках, они нормализуются в presenter layer до `extensions.day_night`.

**Пример структуры RecipeRevisionPhase:**
```sql
CREATE TABLE recipe_revision_phases (
    id BIGSERIAL PK,
    recipe_revision_id BIGINT FK → recipe_revisions,
    phase_index INT,
    name VARCHAR,
    -- Цели по колонкам (не JSON!)
    ph_target DECIMAL(4,2),
    ph_min DECIMAL(4,2),
    ph_max DECIMAL(4,2),
    ec_target DECIMAL(5,2),
    irrigation_mode ENUM('SUBSTRATE', 'RECIRC'),
    irrigation_system_type VARCHAR(32),     -- enum: drip_tape|drip_emitter|ebb_flow|nft|dwc|aeroponics
    substrate_type VARCHAR(64),             -- FK-by-code → substrates.code
    day_night_enabled BOOLEAN,              -- активирует extensions.day_night override
    nutrient_ec_dosing_mode VARCHAR(32),    -- enum: sequential|parallel
    irrigation_interval_sec INT,
    temp_air_target DECIMAL(5,2),
    -- Прогресс
    progress_model VARCHAR, -- TIME|TIME_WITH_TEMP_CORRECTION|GDD
    duration_hours INT,
    base_temp_c DECIMAL(4,2),
    -- Расширения
    extensions JSONB
);
```

### 2.1.1. Новые flat-поля фазы (2026-04-13)

Все поля nullable; полный список колонок — в `../05_DATA_AND_STORAGE/DATA_MODEL_REFERENCE.md` §5.3 / §6.2.

| Поле | Тип | Назначение |
|------|-----|------------|
| `irrigation_system_type` | string(32) | Тип ирригационной системы фазы. Допустимые значения enum: `drip_tape`, `drip_emitter`, `ebb_flow`, `nft`, `dwc`, `aeroponics`. Используется для согласованности с `applicable_systems` выбранного субстрата. |
| `substrate_type` | string(64) | Код субстрата из таблицы `substrates` (`substrates.code`). FK хранится по коду, а не по `id`, чтобы сохранить читаемость snapshot после удаления записи в каталоге. |
| `day_night_enabled` | bool | Если `true` — runtime применяет `extensions.day_night` overrides для pH/EC (см. `EFFECTIVE_TARGETS_SPEC.md` §11) и климатики; если `false`/`null` — overrides игнорируются. |
| `nutrient_ec_dosing_mode` | string(32) | enum `sequential` \| `parallel`. Определяет, дозируются ли компоненты NPK/Ca/Mg/Micro последовательно (`sequential`, по одному с mixing time между шагами) или параллельно (`parallel`, single-step) в irrigation-фазе при EC коррекции. Колонка добавлена миграцией `2026_04_12_200000_add_nutrient_ec_dosing_mode_to_phases.php`. |

Колонки `irrigation_system_type`, `substrate_type`, `day_night_enabled` добавлены миграцией `backend/laravel/database/migrations/2026_04_13_150000_add_system_substrate_daynight_to_phases.php` одновременно в `recipe_revision_phases` (template) и `grow_cycle_phases` (snapshot) — иначе нарушается принцип snapshot immutability (§3.5).

Backend-валидация значений `extensions.day_night` для pH/EC выполняется в `backend/laravel/app/Support/Recipes/RecipePhaseTargetValidator.php:96` (`validateDayNightExtensions`): диапазоны `0..14` (pH) / `0..20` (EC), `min ≤ target ≤ max` для day и night-профиля.

---

### 2.4. Каталог субстратов (`substrates`)

Таблица `substrates` (миграция `backend/laravel/database/migrations/2026_04_13_120000_create_substrates_table.php`) — справочник субстратов, на которые могут ссылаться фазы рецепта через `recipe_revision_phases.substrate_type` (по `code`).

Структура:

| Поле | Тип | Описание |
|------|-----|----------|
| `id` | bigint PK | — |
| `code` | string(64) UNIQUE | Короткий идентификатор (латиница, цифры, `_`); используется как FK-by-code. |
| `name` | string(255) | Человекочитаемое название. |
| `components` | jsonb | Массив `[{name, label, ratio_pct}, ...]`. Сумма `ratio_pct` обязана быть `100%` (валидация в `App\Http\Requests\SubstrateRequest`). |
| `applicable_systems` | jsonb | Массив enum `irrigation_system_type` (см. §2.1.1), для которых субстрат подходит. UI использует это для фильтрации совместимости. |
| `notes` | text nullable | Произвольное описание. |

Модель: `App\Models\Substrate`. Form Request: `App\Http\Requests\SubstrateRequest`. Контроллер: `backend/laravel/app/Http/Controllers/SubstrateController.php`.

REST endpoints (см. также `../04_BACKEND_CORE/REST_API_REFERENCE.md`):

| Метод | Путь | Auth | Назначение |
|-------|------|------|------------|
| GET | `/api/substrates` | sanctum | Список субстратов |
| GET | `/api/substrates/{substrate}` | sanctum | Детали |
| POST | `/api/substrates` | sanctum + agronomist | Создать |
| PATCH | `/api/substrates/{substrate}` | sanctum + agronomist | Обновить |
| DELETE | `/api/substrates/{substrate}` | sanctum + agronomist | Удалить |

Удаление не каскадирует на phase-snapshot: snapshot хранит `substrate_type` как код-строку (см. §3.5).

---

## 3. Новая логика работы (циклы выращивания)

### 3.1. Создание цикла (Wizard)

1. **Агроном выбирает зону** — проверяется, что нет активного цикла
2. **Выбирает растение и рецепт** — только PUBLISHED ревизии
3. **Создаётся GrowCycle** через `GrowCycleService::createCycle()`:
   - `recipe_revision_id` (зафиксированная версия)
   - Создаются снапшоты фаз (`GrowCyclePhase`) из шаблонов
   - `current_phase_id` указывает на первую фазу
4. **Цикл стартует** — `status = RUNNING`, `started_at` заполняется

### 3.2. Работа Python контроллеров

1. **Получение runtime targets** через SQL read-model (AE3):
   - чтение `grow_cycles/grow_cycle_phases` и `automation_effective_bundles`;
   - для `pH/EC target|min|max` канон жёсткий: только `phase snapshot`;
   - `cycle.phase_overrides`, `cycle.manual_overrides` и `zone.logic_profile(active_mode)` могут влиять только на execution/runtime config, но не на chemical setpoints.

2. **Ответ содержит** цели из текущей фазы; execution/runtime настройки могут быть дополнены overrides:
   ```json
   {
     "1": {
       "cycle_id": 123,
       "phase": {"name": "VEG", "started_at": "...", "due_at": "..."},
       "targets": {
         "ph": {"target": 6.0, "min": 5.8, "max": 6.2},
         "ec": {"target": 1.5, "min": 1.3, "max": 1.7},
         "nutrition": {
           "program_code": "MASTERBLEND_3PART_V1",
           "mode": "ratio_ec_pid",
           "solution_volume_l": 100.0,
           "dose_delay_sec": 12,
           "ec_stop_tolerance": 0.07,
           "components": {
             "npk": {"ratio_pct": 46.0, "product_id": 1, "manufacturer": "Masterblend"},
             "calcium": {"ratio_pct": 34.0, "product_id": 2, "manufacturer": "Yara"},
             "magnesium": {"ratio_pct": 17.0, "product_id": 3, "manufacturer": "TerraTarsa"},
             "micro": {"ratio_pct": 3.0, "product_id": 4, "manufacturer": "Haifa"}
           }
         },
         "irrigation": {"mode": "SUBSTRATE", "interval_sec": 3600}
       }
     }
   }
   ```

3. **Контроллеры используют** effective targets для управления оборудованием

### 3.3. Переходы фаз

- **Автоматические**: Через `PhaseProgressEngine` по времени/temperature/GDD
- **Ручные**: Агроном через UI → `POST /api/grow-cycles/{id}/set-phase` или `POST /api/grow-cycles/{id}/advance-phase`
- **История**: Все переходы логируются в `grow_cycle_transitions`

#### Инварианты `GrowCycleService` при смене фазы (2026-04-13)

В начале DB transaction `advancePhase`, `setPhase` и `changeRecipeRevision` берут row-level lock на цикл (`GrowCycle::query()->whereKey($id)->lockForUpdate()->firstOrFail()`) — защита от race condition при параллельных API-вызовах (`backend/laravel/app/Services/GrowCycleService.php:1173,1250,1333`).

После обновления `current_phase_id` (или после смены `recipe_revision_id`) обязательно вызывается `AutomationConfigCompiler::compileAffectedScopes(SCOPE_GROW_CYCLE, $cycleId)` (`GrowCycleService.php:1188,1264,1409`). Это гарантирует, что AE3 при следующем `start-cycle`/`start-irrigation` получит actual targets/ratios/`ec_dosing_mode`/`nutrient_mode`. Пропуск compile приводит к тому, что AE3 продолжает работать со старыми bundles из `automation_effective_bundles`.

#### Семантика `changeRecipeRevision($mode)`

Метод `App\Services\GrowCycleService::changeRecipeRevision()` поддерживает два режима применения новой ревизии (`backend/laravel/app/Services/GrowCycleService.php:1321`):

- **`mode='now'`** — обновляются `recipe_revision_id` и **немедленно** создаётся snapshot первой фазы новой ревизии (`current_phase_id` указывает на новый snapshot). Compiled bundle пересчитывается под новую фазу, AE3 после очередного wake-up получает обновлённые targets.
- **`mode='next_phase'`** — обновляется только `recipe_revision_id`, текущая фаза-snapshot и `current_phase_id` сохраняются. Compiled bundle пересчитывается, но читает старый snapshot. Параметры новой ревизии применяются только при следующем `advancePhase()`, который возьмёт next-фазу из новой ревизии.

> ⚠️ Известный баг (`mode='now'`): создаётся второй snapshot с `phase_index=0`, что нарушает UNIQUE constraint `(grow_cycle_id, phase_index)` на `grow_cycle_phases` (см. §6.2 в DATA_MODEL_REFERENCE). Требует отдельного fix (использовать `max(phase_index)+1` или ослабить constraint).

### 3.4. Overrides (перекрытия)

- Агроном может временно перекрыть параметры цикла
- Хранятся в authority-документах `cycle.phase_overrides` и `cycle.manual_overrides`
- Включаются в effective targets через compiled bundle, без merge через устаревшие таблицы
- Для `pH/EC target|min|max` overrides запрещены: эти поля всегда берутся только из phase snapshot / recipe phase

### 3.5. Snapshot immutability (инвариант)

Ключевой архитектурный инвариант разделения template ↔ snapshot:

- `RecipeRevisionPhase` — **template**, редактируется только пока `recipe_revisions.status = DRAFT`. После `publish` ревизия становится `PUBLISHED` и иммутабельна.
- `GrowCyclePhase` — **snapshot**, копируется из template один раз при `createPhaseSnapshot` (вызывается из `createCycle`, `advancePhase`, `setPhase`, `changeRecipeRevision('now')`).
- AE3 runtime читает только из snapshot (`grow_cycle_phases`), **не** из template. Это обеспечивает воспроизводимость и audit trail.
- Активный цикл (`status IN PLANNED|RUNNING|PAUSED`) может ссылаться только на `PUBLISHED` ревизию.
- Изменение template (через создание новой DRAFT-ревизии и её редактирование) **не влияет** на работающий цикл до явного перехода: `advancePhase` / `setPhase` / `changeRecipeRevision`.
- Bootstrap-материализованные авторити-документы (`source='bootstrap'`) не считаются user-saved для cycle-readiness — `App\Services\ZoneReadinessService::checkRequiredPidConfigs` (`backend/laravel/app/Services/ZoneReadinessService.php:809`) помечает PID как missing, пока пользователь не сохранит конфигурацию явно. Это блокирует start cycle, но не мешает AE3 получить bundle для выполнения операций.

---

## 4. UI / Frontend контракты

### 4.1. `GET /api/recipes/{recipe}/active-usage`

Endpoint возвращает список активных grow-cycle, использующих ревизии данного рецепта. Используется фронтом (`backend/laravel/resources/js/Pages/Recipes/Edit.vue`) для предупреждения "рецепт активен в N зонах — сохранение создаст новую DRAFT-ревизию".

Контроллер: `backend/laravel/app/Http/Controllers/RecipeController.php:89` (`activeUsage`).

Фильтр: только `GrowCycle.status IN (PLANNED, RUNNING, PAUSED)`, связь — через `recipe_revision.recipe_id`.

Response:
```json
{
  "status": "ok",
  "data": {
    "recipe_id": 1,
    "count": 1,
    "active_cycles": [
      {
        "cycle_id": 1,
        "zone_id": 5,
        "zone_name": "Zone A",
        "revision_id": 3,
        "revision_number": 2,
        "status": "RUNNING",
        "started_at": "2026-04-01T10:00:00Z"
      }
    ]
  }
}
```

UI: amber-баннер в редакторе рецепта; сохранение изменений всегда создаёт новую DRAFT-ревизию (PUBLISHED ревизию редактировать запрещено, см. §3.5).

---

## 5. Связь с контроллерами (новая модель)

**Контроллеры получают данные через runtime read-model (AE3):**

1. **Batch read** для нескольких зон:
   - прямые SQL запросы к read-model таблицам;
   - без runtime HTTP запроса к Laravel internal API.

2. **Ответ с полной информацией о циклах:**
   ```json
   {
     "1": {
       "cycle_id": 123,
       "zone_id": 1,
       "phase": {
         "id": 456,
         "name": "Вегетация",
         "code": "VEG",
         "started_at": "2025-01-01T10:00:00Z",
         "due_at": "2025-01-15T10:00:00Z",
         "progress_model": "TIME_WITH_TEMP_CORRECTION"
       },
       "targets": {
         "ph": {"target": 6.0, "min": 5.8, "max": 6.2},
         "ec": {"target": 1.5, "min": 1.3, "max": 1.7},
         "nutrition": {
           "program_code": "MASTERBLEND_3PART_V1",
           "mode": "delta_ec_by_k",
           "solution_volume_l": 100.0,
           "dose_delay_sec": 12,
           "ec_stop_tolerance": 0.07,
           "components": {
             "npk": {"ratio_pct": 44.0, "dose_ml_per_l": 1.8, "k_ms_per_ml_l": 0.80, "product_id": 1, "manufacturer": "Masterblend"},
             "calcium": {"ratio_pct": 36.0, "dose_ml_per_l": 1.2, "k_ms_per_ml_l": 0.65, "product_id": 2, "manufacturer": "Yara"},
             "magnesium": {"ratio_pct": 17.0, "dose_ml_per_l": 0.5, "k_ms_per_ml_l": 0.35, "product_id": 3, "manufacturer": "TerraTarsa"},
             "micro": {"ratio_pct": 3.0, "dose_ml_per_l": 0.2, "k_ms_per_ml_l": 0.15, "product_id": 4, "manufacturer": "Haifa"}
           }
         },
         "irrigation": {
           "mode": "SUBSTRATE",
           "interval_sec": 3600,
           "duration_sec": 300
         },
         "lighting": {
           "photoperiod_hours": 18,
           "start_time": "06:00:00"
         },
         "climate_request": {
           "temp_air_target": 25.0,
           "humidity_target": 60.0,
           "co2_target": 800
         }
       }
     }
   }
   ```

3. **Контроллеры используют структурированные данные** для принятия решений

Поддерживаемые режимы `targets.nutrition.mode`:
- `ratio_ec_pid` — базовый PID по EC с распределением доз по `ratio_pct`;
- `delta_ec_by_k` — расчёт доз по `ΔEC`, `ratio_pct`, `k_ms_per_ml_l` и `solution_volume_l`;
- `dose_ml_l_only` — дозирование по фиксированным `dose_ml_per_l`.

Строгое правило схемы питания:
- используются 4 компонента (`npk`, `calcium`, `magnesium`, `micro`);
- API фаз требует заполнения всех 4 `*_ratio_pct`;
- fallback на старую 3-компонентную схему не поддерживается.

---

## 6. Правила для ИИ-агентов (после рефакторинга)

### 6.1. Обязательные правила

1. **Всегда использовать GrowCycle как центр истины** — не ссылаться на zone_recipe_instances
2. **Версионировать рецепты** — новые изменения через RecipeRevision, а не прямое редактирование
3. **Обновлять effective targets контракт** — при добавлении новых полей в цели
4. **Тестировать контракты** — изменения в EffectiveTargetsService требуют обновления тестов
5. **Разделять read-path по назначению** — UI и integration tooling используют Laravel API, runtime automation-engine использует direct SQL read-model

### 6.2. Новая модель данных

- **RecipeRevision** — для версионирования рецептов
- **GrowCycle** — для активных циклов (1 на зону)
- **GrowCyclePhase** — снапшоты фаз (не ссылаются на шаблоны)
- **EffectiveTargetsService** — Laravel business/read-model для targets и integration contracts

### 6.3. Запреты

- ❌ Не добавлять поля в JSON targets — использовать колонки
- ❌ Не создавать новые связи без GrowCycle
- ❌ Не обходить версионирование рецептов
- ❌ Не делать прямые SQL запросы из Python в recipe_* таблицы

**Recipe Engine — это система версионированных целей с центром в GrowCycle.**
