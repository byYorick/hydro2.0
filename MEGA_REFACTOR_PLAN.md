# MEGA_REFACTOR_PLAN.md
# Hydro2.0 — Мега‑план рефакторинга под новую доменную архитектуру (без обратной совместимости)

Дата: 2025‑12‑25

## 0) Цель (Definition of Done)
Система переводится на доменную модель:

**Теплица → Зоны → Цикл выращивания (центр истины) → Растение → Рецепты → Фазы (+ опциональные подшаги)**

и больше не использует старую ось `zone_recipe_instances + recipe_phases.targets`.

**Готово**, когда:
- В каждой зоне enforced: **ровно 1 активный цикл** (RUNNING/PAUSED; опционально 1 PLANNED).
- Python‑контроллеры и Scheduler читают **только** active `grow_cycles` и **effective targets** текущей фазы (с учётом override’ов).
- UI “Центр циклов” + “Мастер цикла” работают на новой модели, без legacy‑страниц/эндпоинтов.
- Рецепты поддерживают **ревизии**: редактирование текущего DRAFT и **клонирование** (create new from existing), публикация/заморозка.
- Переходы фаз логируются, возможны: авто по времени + ручной switch с комментарием.
- Команды имеют **двухфазное подтверждение** (ACK + DONE/ERROR) и отображаются в UI/логах.
- Убраны дубли/архив‑таблицы, включены retention/partitioning политики; код больше не пишет в “_archive”.

## 1) Контекст и принятые инварианты (из ваших ответов)
### 1.1. Топология оборудования
- **1 зона = 1 контур** полива/подготовки раствора; зоны **не делят** контуры.
- В зоне: **1 полив**, **1 туман**, **2 бака** (чистая вода + рабочий раствор).
- Туман: и орошение, и внесение СЗР (единый контур, разные режимы/рецепты).
- **1 система досвечивания** на зону.
- **Климат (вентиляция/проветривание/подогрев)** — **общий на теплицу**.

### 1.2. Сенсоры
- В зоне допускаются сенсоры T/RH/CO₂ и т.д.
- В теплице также есть сенсоры внутри и снаружи + датчик ветра снаружи.

### 1.3. Ноды и знания
- **1 нода = 1 зона** (целевой принцип).
- Ноды знают **только** `{greenhouse_id/uid, zone_id/uid}`. Вся логика/рецепты/циклы — на сервере.

### 1.4. Циклы
- **1 активный цикл на зону**.
- Цикл **жёстко связан** с одним растением.
- Завершение: по времени + ручное подтверждение/закрытие (агроном).
- Текущая фаза хранится в БД.
- Рецепт можно корректировать “на лету”.
- Управлять циклами может **только агроном**.
- Допускаются **внецикловые команды**.
- Команда: **двухфазное подтверждение** выполнения.

## 2) Короткий аудит текущего состояния (по репозиторию ref_front)
Ключевые проблемы/несостыковки в текущем коде/доках:
1. **Две параллельные оси истины**:  
   - legacy: `zone_recipe_instances.current_phase_index + recipe_phases.targets(JSONB)`  
   - новая: `grow_cycles` + `grow_stage_templates/recipe_stage_maps`  
   При этом Python‑сервисы (automation‑engine, scheduler) всё ещё массово читают legacy‑таблицы и используют targets из JSON.
2. `grow_cycles` сейчас содержит ссылки на `zone_recipe_instance_id` и “fallback targets из фазы”, что делает цикл не самостоятельным.
3. `recipe_phases.targets` = JSONB → слабая валидация, трудный UI, нет строгих запросов/индексов.
4. Нет полноценной **версии/ревизий рецептов**, а требования прямо подразумевают `edit current` vs `clone new`.
5. Моделирование климата “общего на теплицу” в БД/привязках оборудования выражено слабо (в основном всё zone‑scoped).
6. Есть “архивные” таблицы/дубли в слоях хранения; retention/partitioning частично уже внедрены, но хвосты остаются.

## 3) Целевая доменная модель (новая, каноническая)
### 3.1. ERD (в терминах сущностей)
- `greenhouses` 1—N `zones`
- `zones` 1—1 `grow_cycles` (active) / 1—N (history)
- `plants` 1—N `recipes` (через pivot `plant_recipe` или прямую FK — выбрать один вариант и закрепить)
- `recipes` 1—N `recipe_revisions`
- `recipe_revisions` 1—N `recipe_revision_phases` 1—N `recipe_revision_phase_steps`
- `grow_cycles` → `recipe_revisions` (зафиксированная ревизия, чтобы активный цикл не “плыл”)
- `grow_cycles` хранит текущую фазу/шаг и временные отметки, overrides и переходы логируются
- `nodes` принадлежат `greenhouse`, (обычно) привязаны к `zone`; 1 зона = 1 node (enforced)
- `infrastructure_instances` (полиморфный owner: zone|greenhouse) + `channel_bindings`
- `telemetry_*`, `commands`, `zone_events`, `alerts` остаются как “операционная шина”, но обновляются под новые entity_type/type

### 3.2. Ключевой принцип: “центр истины” = GrowCycle
- Python‑контроллеры вычисляют цели **не из зоны**, а из:  
  `active_grow_cycle` → `current_phase` → `effective targets` (phase setpoints + overrides)
- У зоны остаются: профиль железа/контуров, capabilities, water_state, привязки каналов.

## 4) План работ (один мега‑тикет, разбитый на этапы)
Ниже — последовательность работ для исполнителя‑ИИ (или команды), без обратной совместимости.

### ✅ Этап 0. "Заморозка" базиса и стратегия ветки
1. ✅ Создать ветку `refactor/grow-cycle-centric`.
2. ✅ Зафиксировать тестовый контур:
   - `php artisan test` (что проходит/падает)
   - `pytest` по сервисам
   - e2e (если есть)
3. ✅ Ввести правило: все миграции — под `migrate:fresh` (т.к. backward compat не нужна).

✅ Acceptance:
- Ветка собирается, Docker поднимается, есть базовый smoke‑test.

---

### ✅ Этап 1. Пересборка схемы БД под новую доменную модель
#### ✅ 1.1. Новые таблицы/поля (миграции Laravel)
Сделать **новый набор миграций** (или 1 "mega migration" + вспомогательные), который:
- ✅ Создаёт:
  - ✅ `recipe_revisions`
  - ✅ `recipe_revision_phases` (targets "по колонкам", JSON оставить только для расширений)
  - ✅ `recipe_revision_phase_steps` (опционально)
  - ✅ `grow_cycle_overrides` (опционально: либо таблица, либо jsonb в grow_cycles, но таблица лучше для аудита)
  - ✅ `grow_cycle_transitions`
- ✅ Модифицирует `grow_cycles`:
  - ✅ удалить `zone_recipe_instance_id`
  - ✅ добавить `recipe_revision_id` (NOT NULL)
  - ✅ добавить `current_phase_id` (FK → recipe_revision_phases.id) и `current_step_id` (FK nullable)
  - ✅ добавить `phase_started_at`, `step_started_at`, `planting_at` (если нет) и `progress_meta jsonb` (для temp/light коррекций)
- ✅ Полиморфная инфраструктура (рекомендуется):
  - ✅ заменить `zone_infrastructure` + `infrastructure_assets` на единый `infrastructure_instances`:
    - ✅ `owner_type` ENUM('zone','greenhouse')
    - ✅ `owner_id`
    - ✅ `asset_type` (PUMP/MISTER/TANK_CLEAN/TANK_WORKING/LIGHT/VENT/HEATER/…)
    - ✅ `label`, `specs`, `required`
  - ✅ заменить `zone_channel_bindings` на `channel_bindings` (owner‑agnostic):
    - ✅ `infrastructure_instance_id`
    - ✅ `node_id`
    - ✅ `channel`
    - ✅ `direction`, `role`
- ⏳ Enforce "1 node = 1 zone":
  - ⏳ частичный уникальный индекс: `nodes(zone_id) WHERE zone_id IS NOT NULL` (или `unique` + договориться что только 1 node будет иметь zone_id).

#### ✅ 1.2. Дроп legacy таблиц и колонок
✅ Удалить из схемы (и затем удалить код/модели):
- ✅ `zone_recipe_instances`
- ✅ `recipe_phases` (legacy JSON targets)
- ✅ `zone_cycles`
- ✅ `plant_cycles` (дублирование состояния цикла)
- ✅ `commands_archive`, `zone_events_archive` (и любые *_archive где это "дубли")
- ✅ `recipe_stage_maps` — удалено (используется вариант Б)

#### ✅ 1.3. Stage templates (UI)
✅ Оставить `grow_stage_templates` как справочник UI.  
✅ Реализован вариант Б: в `recipe_revision_phases` добавлен `stage_template_id`

#### ✅ 1.4. Ограничения целостности
- ✅ Уникальность активного цикла:
  - ✅ partial unique index на `grow_cycles(zone_id)` WHERE `status IN ('RUNNING','PAUSED')`
  - ⏳ опционально дополнительно ограничить 1 PLANNED (если нужно).
- ✅ Упорядочивание фаз:
  - ✅ `unique(recipe_revision_id, phase_index)`.

✅ Acceptance:
- ✅ `php artisan migrate:fresh` проходит.
- ✅ Схема соответствует новой модели, legacy таблиц нет.

---

### ✅ Этап 2. Laravel Backend: модели, сервисы, API, события
#### ✅ 2.1. Eloquent модели и отношения
✅ Создать/обновить:
- ✅ `Recipe`, `RecipeRevision`, `RecipeRevisionPhase`, `RecipeRevisionPhaseStep`
- ✅ `GrowCycle` (центр истины), `GrowCycleTransition`, `GrowCycleOverride`
- ✅ `InfrastructureInstance`, `ChannelBinding`
- ✅ удалить `ZoneRecipeInstance`, `PlantCycle`, `ZoneCycle`

✅ Acceptance:
- ✅ Tinker: `Zone::with('activeGrowCycle.currentPhase')` работает.

#### ✅ 2.2. "Effective targets" — единый контракт для Python
✅ Добавить сервис (например `EffectiveTargetsService`) который по `grow_cycle_id` возвращает:
- ✅ `phase_targets` (колонки)
- ✅ `overrides` (табличные + computed)
- ✅ `effective` (слияние)
- ✅ meta: `phase_id`, `phase_name`, `phase_due_at`, `progress_model`

✅ Стабилизировать контракт JSON:
```json
{
  "cycle_id": 123,
  "zone_id": 5,
  "phase": { "id": 77, "code": "VEG", "started_at": "...", "due_at": "..." },
  "targets": {
    "ph": {"target": 5.8, "min": 5.6, "max": 6.0},
    "ec": {"target": 1.6, "min": 1.4, "max": 1.8},
    "irrigation": {...},
    "mist": {...},
    "lighting": {...},
    "climate_request": {...}
  }
}
```

#### ✅ 2.3. API эндпоинты (перепроектирование)
✅ Сделать новый набор эндпоинтов и удалить legacy:

**Циклы**
- ✅ `GET /api/zones/{zone}/grow-cycle` → возвращает active cycle + effective targets + прогресс
- ✅ `POST /api/zones/{zone}/grow-cycles` → создать новый цикл (агроном)
- ✅ `POST /api/grow-cycles/{id}/pause|resume|harvest|abort`
- ✅ `POST /api/grow-cycles/{id}/set-phase` (manual, с comment)
- ✅ `POST /api/grow-cycles/{id}/advance-phase` (next)
- ✅ `POST /api/grow-cycles/{id}/change-recipe-revision` (apply now / at next phase)

**Рецепты/ревизии**
- ⏳ `POST /api/recipes` / `PATCH /api/recipes/{id}` (базовые CRUD, не входили в Этап 2)
- ✅ `POST /api/recipes/{id}/revisions` (clone from revision_id)
- ✅ `PATCH /api/recipe-revisions/{rev}` (edit draft)
- ✅ `POST /api/recipe-revisions/{rev}/publish` (lock)
- ✅ `GET /api/recipe-revisions/{rev}` (full with phases)

**Инфраструктура**
- ✅ CRUD для `infrastructure_instances` и `channel_bindings`
- ✅ отдельный раздел "климат теплицы" (greenhouse owner)

✅ Удалить:
- ✅ `/attach-recipe`, `/zone_recipe_instances/*`, любые endpoints которые выставляют targets в JSON напрямую.

#### ✅ 2.4. Права доступа
- ✅ Только роль/permission "agronomist":
  - ✅ create/stop cycle
  - ✅ edit recipes & publish
  - ✅ manual phase switch
- ✅ Остальные: read‑only + manual внецикловые команды (по отдельной политике, если нужно).
- ✅ Созданы Policy: `GrowCyclePolicy`, `RecipeRevisionPolicy`
- ✅ Все методы управления защищены проверками прав через `Gate::allows()`

#### 2.5. События и логи
- Все transition’ы цикла писать в:
  - `grow_cycle_transitions`
  - `zone_events` (entity_type='grow_cycle', type='CYCLE_*')
- WebSocket broadcast: `GrowCycleUpdated` расширить payload (phase, targets summary).

Acceptance:
- Backend API отдаёт active cycle и effective targets.
- Legacy контроллеры/маршруты удалены, сборка проходит.

---

### Этап 3. Python services: automation-engine, scheduler, history-logger, digital-twin
#### 3.1. Удалить чтение legacy таблиц
Во всех сервисах:
- заменить запросы `zone_recipe_instances + recipe_phases` на:
  - `grow_cycles` + `recipe_revisions` + `recipe_revision_phases` (+ overrides)
  - или на вызов Laravel endpoint “effective targets” (рекомендуется, чтобы логика слияния была в одном месте)

Рекомендация:  
- В automation-engine: **batch‑endpoint** в Laravel:
  - `POST /api/internal/effective-targets/batch` с `zone_ids[]` → вернуть targets по зонам.

#### 3.2. Phase Progress Engine (авто прогресс фаз)
Варианты прогресса:
- `TIME` (по duration)
- `TIME_WITH_TEMP_CORRECTION` (простая коррекция по avg temp)
- `GDD` (градусо‑дни) и/или `DLI` (позже)

MVP реализация:
- хранить в `grow_cycles.progress_meta`:
  - `temp_avg_24h`, `light_dli_24h`, `speed_factor`, `computed_due_at`
- авто переход по `computed_due_at`, но **возможна ручная коррекция**.

Обязательные свойства:
- идемпотентность (повторный запуск не ломает)
- защита от гонок (advisory lock на `grow_cycle_id`)

#### 3.3. Scheduler
- `get_active_schedules()` → брать расписания из effective targets (irrigation/lighting/mist).
- Команды отправлять через единый путь (как сейчас через automation-engine), но контекст команды должен включать:
  - `cycle_id` (если команда в рамках цикла)
  - `source = cycle|manual|system`

#### 3.4. Двухфазное подтверждение команд
- Стандартизировать:
  - `command.request_id` (uuid)
  - топики ACK и RESULT (или один status с state)
- history-logger:
  - при получении ACK → `commands.ack_at`, `status='ACK'`
  - при RESULT → `executed_at`, `status='DONE'|'ERROR'`, заполнить error_code/message, duration_ms
- automation-engine:
  - если нужно “ожидать” выполнения, делать polling по commands (но лучше не блокировать control loop)

#### 3.5. Digital Twin
- Изменить источники истины: twin состояния зоны должен отражать:
  - active cycle + phase + effective targets
  - last telemetry
  - last commands status

Acceptance:
- automation-engine и scheduler стартуют без ошибок.
- В логах нет обращений к `zone_recipe_instances`/`recipe_phases`.

---

### Этап 4. Frontend (Inertia/Vue): приведение UI/UX к новой модели
#### 4.1. Центр циклов (Cycles/Center.vue)
- Отображать:
  - список зон
  - активный цикл (plant, recipe revision, phase, progress)
  - быстрые действия (pause/resume, manual phase switch, harvest)
- Таймлайн фаз: строить по `recipe_revision_phases` (stage_template_id как UI‑лейбл).

#### 4.2. Мастер создания цикла (GrowCycles/Wizard.vue)
- Сценарий:
  1) выбрать зону
  2) выбрать растение
  3) выбрать рецепт → выбрать ревизию (published)
  4) посадка/старт, batch_label, заметки
  5) подтверждение “в зоне будет 1 активный цикл”
- После создания: редирект в Центр циклов.

#### 4.3. Редактор рецептов с ревизиями
- Список рецептов по растению
- Для рецепта: вкладка “Ревизии”:
  - Draft редактируется
  - Published readonly
  - “Создать новую на основе” (clone)
  - “Опубликовать” (lock)
- Редактор фаз:
  - ph/ec/irrigation — обязательные поля
  - остальное optional
  - шаги (optional): таблица подшагов с offset и action/task

#### 4.4. Удаление legacy UI
- удалить страницы, которые привязаны к `zone_recipe_instances`/`recipe_phases.targets`
- обновить composables/api clients

#### 4.5. Ручные операции
- Manual switch phase: обязательный comment.
- Change recipe on the fly:
  - либо “переключить ревизию сейчас” (и сбросить фазу по mapping)
  - либо “с следующей фазы”.

Acceptance:
- UI не обращается к legacy API.
- Создание/управление циклом работает end‑to‑end.

---

### Этап 5. Очистка хранения, retention/partitioning, удаление дублей
1. Удалить “архивные” таблицы и код, который туда пишет.
2. Проверить Timescale retention policies:
   - telemetry_samples (90d) уже есть — оставить/сделать конфигурируемым
   - агрегаты оставить только если реально используются (иначе удалить)
3. Для `commands` и `zone_events`:
   - добавить партиционирование по времени (Postgres native partitions) **или** Timescale hypertable, если объёмы большие
   - policy retention (например 365 дней) + агрегированные “сводки” для UI

Acceptance:
- Нет дублей таблиц.
- Retention управляется политиками, а не “ручными” archive‑таблицами.

---

### Этап 6. Тестирование и стабилизация
1. Backend:
   - Feature tests: создание цикла, pause/resume, manual phase switch, change recipe revision, права агронома
   - Contract tests: effective targets shape
2. Python:
   - pytest: batch fetch targets, phase progression idempotency, command ack flow
3. E2E:
   - сценарий “создать рецепт→ревизию→цикл→переключить фазу→завершить”

Acceptance:
- CI зелёный.
- Нет “скрытых” путей, использующих legacy сущности.

---

### Этап 7. Документация (обязательная часть, иначе система опять расползётся)
Обновить в `doc_ai` минимум:
- `LOGIC_ARCH.md` — добавить GrowCycle как центр истины, убрать zone_recipe_instances
- `DATA_MODEL_REFERENCE.md` — новая схема таблиц, удалить legacy
- `RECIPE_ENGINE_FULL.md` + `HYDROPONIC_RECIPES_ENGINE.md` — ревизии, фазы по колонкам, шаги
- `FRONTEND_ARCH_FULL.md` — новые страницы/контракты
- `PYTHON_SERVICES_ARCH.md` — новые источники targets, batch endpoints
- Добавить “RFC” файл: `doc_ai/00_RFC/GROW_CYCLE_CENTRIC_ARCH.md` с инвариантами

Acceptance:
- Документация согласована с кодом, нет противоречий.

## 5) Рекомендованный минимальный набор колонок для `recipe_revision_phases`
Обязательные (MVP):
- `ph_target`, `ph_min`, `ph_max`
- `ec_target`, `ec_min`, `ec_max`
- `irrigation_mode` ENUM('SUBSTRATE','RECIRC')
- `irrigation_interval_sec`, `irrigation_duration_sec`

Опциональные:
- `lighting_photoperiod_hours`, `lighting_start_time`
- `mist_interval_sec`, `mist_duration_sec`, `mist_mode` (NORMAL|SPRAY)
- `temp_air_target`, `humidity_target`, `co2_target` (как “запрос зоны” к климату теплицы)
- `progress_model`, `duration_hours|days`, `base_temp_c`, `target_gdd`, `dli_target`

## 6) Список “что точно удалить из кода” (после миграций)
- Все упоминания:
  - `zone_recipe_instances`
  - `recipe_phases.targets`
  - контроллеры/страницы “attach recipe to zone”
  - репозитории Python: `recipe_utils.py` в legacy варианте, SQL JOIN на zone_recipe_instances
- Таблицы/модели:
  - `PlantCycle`, `ZoneCycle`, `ZoneRecipeInstance`
- Старые доки, запрещающие breaking changes (теперь breaking changes разрешены, но фиксируются RFC)

MD