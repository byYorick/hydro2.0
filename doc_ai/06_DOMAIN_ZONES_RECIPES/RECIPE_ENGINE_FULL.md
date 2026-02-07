# RECIPE_ENGINE_FULL.md
# Полная архитектура Recipe Engine 2.0 (ОБНОВЛЕНО ПОСЛЕ РЕФАКТОРИНГА 2025-12-25)

Recipe Engine — это подсистема, которая управляет рецептами выращивания:
версиями рецептов, фазами с целями по колонкам, циклами выращивания и effective targets.

**КЛЮЧЕВЫЕ ИЗМЕНЕНИЯ ПОСЛЕ РЕФАКТОРИНГА:**
- ✅ Убрана модель `zone_recipe_instances` + JSON targets
- ✅ Введено версионирование через `RecipeRevision`
- ✅ Центр истины — `GrowCycle` вместо `Zone`
- ✅ Цели хранятся по колонкам, а не в JSON
- ✅ Единый контракт через `EffectiveTargetsService`


Compatible-With: Protocol 2.0, Backend >=3.0, Python >=3.0, Database >=3.0, Frontend >=3.0.
Breaking-change: legacy форматы/алиасы удалены, обратная совместимость не поддерживается.

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

1. **Получение effective targets** через Laravel API:
   ```bash
   POST /api/internal/effective-targets/batch
   {"zone_ids": [1, 2, 3]}
   ```

2. **Ответ содержит** цели из текущей фазы с учётом overrides:
   ```json
   {
     "1": {
       "cycle_id": 123,
       "phase": {"name": "VEG", "started_at": "...", "due_at": "..."},
       "targets": {
         "ph": {"target": 6.0, "min": 5.8, "max": 6.2},
         "ec": {"target": 1.5, "min": 1.3, "max": 1.7},
         "nutrition": {
           "program_code": "GENERIC_3PART_V1",
           "components": {
             "npk": {"ratio_pct": 46.0},
             "calcium": {"ratio_pct": 34.0},
             "micro": {"ratio_pct": 20.0}
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
- **Ручные**: Агроном через UI → `POST /api/grow-cycles/{id}/set-phase`
- **История**: Все переходы логируются в `grow_cycle_transitions`

### 3.4. Overrides (перекрытия)

- Агроном может временно перекрыть параметры цикла
- Хранятся в `grow_cycle_overrides` с `is_active` флагом
- Включаются в effective targets автоматически

---

## 4. Связь с контроллерами (новая модель)

**Контроллеры получают данные через EffectiveTargetsService:**

1. **Batch запрос** для нескольких зон:
   ```bash
   POST /api/internal/effective-targets/batch
   Content-Type: application/json
   Authorization: Bearer <token>

   {"zone_ids": [1, 2, 3]}
   ```

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
           "program_code": "GENERIC_3PART_V1",
           "components": {
             "npk": {"ratio_pct": 46.0, "dose_ml_per_l": 1.8},
             "calcium": {"ratio_pct": 34.0, "dose_ml_per_l": 1.2},
             "micro": {"ratio_pct": 20.0, "dose_ml_per_l": 0.6}
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

---

## 5. Правила для ИИ-агентов (после рефакторинга)

### 5.1. Обязательные правила

1. **Всегда использовать GrowCycle как центр истины** — не ссылаться на zone_recipe_instances
2. **Версионировать рецепты** — новые изменения через RecipeRevision, а не прямое редактирование
3. **Обновлять effective targets контракт** — при добавлении новых полей в цели
4. **Тестировать контракты** — изменения в EffectiveTargetsService требуют обновления тестов
5. **Использовать Laravel API** — Python сервисы не делают прямые SQL запросы

### 5.2. Новая модель данных

- **RecipeRevision** — для версионирования рецептов
- **GrowCycle** — для активных циклов (1 на зону)
- **GrowCyclePhase** — снапшоты фаз (не ссылаются на шаблоны)
- **EffectiveTargetsService** — единый источник целей для Python

### 5.3. Запреты

- ❌ Не добавлять поля в JSON targets — использовать колонки
- ❌ Не создавать новые связи без GrowCycle
- ❌ Не обходить версионирование рецептов
- ❌ Не делать прямые SQL запросы из Python в recipe_* таблицы

**Recipe Engine — это система версионированных целей с центром в GrowCycle.**
