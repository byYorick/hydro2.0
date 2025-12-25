# Аудит Этапа 2: Laravel Backend

Дата: 2025-12-25

## ✅ 2.1. Eloquent модели и отношения

### Созданные модели:
- ✅ `RecipeRevision` - создана, relationships OK
- ✅ `RecipeRevisionPhase` - создана, relationships OK
- ✅ `RecipeRevisionPhaseStep` - создана, relationships OK
- ✅ `GrowCycle` - создана, relationships OK
- ✅ `GrowCycleTransition` - создана, relationships OK
- ✅ `GrowCycleOverride` - создана, relationships OK
- ✅ `GrowCyclePhase` - создана (снапшот), relationships OK
- ✅ `GrowCyclePhaseStep` - создана (снапшот), relationships OK
- ✅ `InfrastructureInstance` - создана, relationships OK
- ✅ `ChannelBinding` - создана, relationships OK

### Legacy модели (требуют удаления):
- ❌ `ZoneRecipeInstance` - **ВСЕ ЕЩЕ ИСПОЛЬЗУЕТСЯ** в 12 файлах:
  - `app/Models/Zone.php` - метод `recipeInstance()` помечен как @deprecated
  - `app/Services/GrowCycleService.php` - импорт, но не используется
  - `app/Services/ZoneService.php` - методы `attachRecipe()`, `changePhase()`, `nextPhase()` используют legacy модель
  - `app/Services/RecipeService.php` - методы используют legacy модель
  - `app/Http/Controllers/GrowCycleWizardController.php` - использует legacy модель
  - `app/Http/Controllers/ZoneController.php` - импорт
  - `app/Models/Recipe.php` - relationship `zoneRecipeInstances()`
  - `app/Http/Controllers/SimulationController.php` - использует
  - `app/Services/RecipeAnalyticsService.php` - использует
  - `app/Jobs/CalculateRecipeAnalyticsJob.php` - использует
  - `app/Console/Commands/FixZone6Command.php` - использует
  - `app/Models/ZoneRecipeInstance.php` - сама модель существует

- ❌ `PlantCycle` - **ВСЕ ЕЩЕ ИСПОЛЬЗУЕТСЯ**:
  - `app/Models/Plant.php` - relationship `cycles()` → `PlantCycle`
  - `app/Models/PlantCycle.php` - модель существует

- ❌ `ZoneCycle` - **ВСЕ ЕЩЕ ИСПОЛЬЗУЕТСЯ**:
  - `app/Http/Controllers/ZoneCommandController.php` - использует для проверки активного цикла
  - `app/Models/ZoneCycle.php` - модель существует

### Acceptance:
- ✅ Tinker: `Zone::with('activeGrowCycle.currentPhase')` - проверено (нет зон в БД, но синтаксис правильный)

## ✅ 2.2. "Effective targets" — единый контракт для Python

### Сервис:
- ✅ `EffectiveTargetsService` - создан и реализован
- ✅ Метод `getEffectiveTargets(int $growCycleId)` - реализован
- ✅ Метод `getEffectiveTargetsBatch(array $growCycleIds)` - реализован
- ✅ Поддержка снапшотов (`GrowCyclePhase`) и шаблонов (`RecipeRevisionPhase`)
- ✅ Слияние overrides с базовыми параметрами
- ✅ Вычисление `phase_due_at` и `progress_model`

### JSON контракт:
- ✅ Структура соответствует плану:
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

## ✅ 2.3. API эндпоинты (перепроектирование)

### Циклы:
- ✅ `GET /api/zones/{zone}/grow-cycle` - реализован (`GrowCycleController::getActive`)
- ✅ `POST /api/zones/{zone}/grow-cycles` - реализован (`GrowCycleController::store`)
- ✅ `POST /api/grow-cycles/{id}/pause` - реализован (`GrowCycleController::pause`)
- ✅ `POST /api/grow-cycles/{id}/resume` - реализован (`GrowCycleController::resume`)
- ✅ `POST /api/grow-cycles/{id}/harvest` - реализован (`GrowCycleController::harvest`)
- ✅ `POST /api/grow-cycles/{id}/abort` - реализован (`GrowCycleController::abort`)
- ✅ `POST /api/grow-cycles/{id}/set-phase` - реализован (`GrowCycleController::setPhase`)
- ✅ `POST /api/grow-cycles/{id}/advance-phase` - реализован (`GrowCycleController::advancePhase`)
- ✅ `POST /api/grow-cycles/{id}/change-recipe-revision` - реализован (`GrowCycleController::changeRecipeRevision`)

### Рецепты/ревизии:
- ⏳ `POST /api/recipes` / `PATCH /api/recipes/{id}` - не входили в Этап 2
- ✅ `POST /api/recipes/{id}/revisions` - реализован (`RecipeRevisionController::store`)
- ✅ `PATCH /api/recipe-revisions/{rev}` - реализован (`RecipeRevisionController::update`)
- ✅ `POST /api/recipe-revisions/{rev}/publish` - реализован (`RecipeRevisionController::publish`)
- ✅ `GET /api/recipe-revisions/{rev}` - реализован (`RecipeRevisionController::show`)

### Фазы рецептов:
- ✅ `POST /api/recipe-revisions/{rev}/phases` - реализован (`RecipeRevisionPhaseController::store`)
- ✅ `PATCH /api/recipe-revision-phases/{phase}` - реализован (`RecipeRevisionPhaseController::update`)
- ✅ `DELETE /api/recipe-revision-phases/{phase}` - реализован (`RecipeRevisionPhaseController::destroy`)

### Инфраструктура:
- ✅ `GET /api/zones/{zone}/infrastructure-instances` - реализован (`InfrastructureInstanceController::indexForZone`)
- ✅ `GET /api/greenhouses/{greenhouse}/infrastructure-instances` - реализован (`InfrastructureInstanceController::indexForGreenhouse`)
- ✅ `POST /api/infrastructure-instances` - реализован (`InfrastructureInstanceController::store`)
- ✅ `PATCH /api/infrastructure-instances/{id}` - реализован (`InfrastructureInstanceController::update`)
- ✅ `DELETE /api/infrastructure-instances/{id}` - реализован (`InfrastructureInstanceController::destroy`)

### Привязки каналов:
- ✅ CRUD для `channel_bindings` - реализован через `ChannelBindingController`

### Legacy endpoints:
- ✅ Удалены `/attach-recipe`, `/zone_recipe_instances/*` - проверено в routes/api.php

## ✅ 2.4. Права доступа

### Policies:
- ✅ `GrowCyclePolicy` - создана
  - ✅ `manage()` - проверка роли 'agronomist'
  - ✅ `create()` - проверка роли 'agronomist'
  - ✅ `update()` - проверка роли 'agronomist'
  - ✅ `view()` - все авторизованные
  - ✅ `switchPhase()` - проверка роли 'agronomist'
  - ✅ `changeRecipeRevision()` - проверка роли 'agronomist'

- ✅ `RecipeRevisionPolicy` - создана
  - ✅ `manage()` - проверка роли 'agronomist'
  - ✅ `create()` - проверка роли 'agronomist'
  - ✅ `update()` - проверка роли 'agronomist' + статус 'DRAFT'
  - ✅ `publish()` - проверка роли 'agronomist' + статус 'DRAFT'
  - ✅ `view()` - все авторизованные

### Использование в контроллерах:
- ✅ `GrowCycleController` - использует `Gate::allows()` для всех мутирующих операций
- ✅ `RecipeRevisionController` - использует `Gate::allows()` для всех мутирующих операций

## ✅ 2.5. События и логи

### Требования:
- ✅ **РЕАЛИЗОВАНО**: Все transition'ы цикла пишутся в `grow_cycle_transitions`
- ✅ **РЕАЛИЗОВАНО**: События пишутся в `zone_events` (entity_type='grow_cycle', type='CYCLE_*')
- ⚠️ **ЧАСТИЧНО РЕАЛИЗОВАНО**: WebSocket broadcast `GrowCycleUpdated` существует, но payload может быть расширен

### Реализация:
- ✅ `GrowCycleService::create()` - создает запись в `grow_cycle_transitions` с trigger='CYCLE_CREATED'
- ✅ `GrowCycleService::pause()` - создает запись в `zone_events` с type='CYCLE_PAUSED'
- ✅ `GrowCycleService::resume()` - создает запись в `zone_events` с type='CYCLE_RESUMED'
- ✅ `GrowCycleService::harvest()` - создает запись в `zone_events` с type='CYCLE_HARVESTED'
- ✅ `GrowCycleService::abort()` - создает запись в `zone_events` с type='CYCLE_ABORTED'
- ✅ `GrowCycleService::advancePhase()` - создает запись в `grow_cycle_transitions` и `zone_events` с type='CYCLE_PHASE_ADVANCED'
- ✅ `GrowCycleService::setPhase()` - создает запись в `grow_cycle_transitions` и `zone_events` с type='CYCLE_PHASE_SET'
- ✅ `GrowCycleService::changeRecipeRevision()` - создает запись в `zone_events` с type='CYCLE_RECIPE_REVISION_CHANGED'
- ✅ Все операции отправляют WebSocket broadcast через `GrowCycleUpdated` event

### Замечания:
- ⚠️ `GrowCycleTransition` использует `from_phase_id` и `to_phase_id`, которые ссылаются на `RecipeRevisionPhase` (шаблоны), а не на `GrowCyclePhase` (снапшоты). Это может быть проблемой, если нужно отслеживать переходы между снапшотами.

## 📊 Итоговый статус

### ✅ Выполнено:
- ✅ Все модели созданы и relationships работают
- ✅ EffectiveTargetsService реализован полностью
- ✅ Все API эндпоинты реализованы
- ✅ Policies созданы и используются в контроллерах

### ❌ Требует исправления:
1. **Legacy модели все еще используются:**
   - `ZoneRecipeInstance` - 12 файлов
   - `PlantCycle` - 2 файла
   - `ZoneCycle` - 2 файла

2. **Потенциальная проблема с `GrowCycleTransition`:**
   - `from_phase_id` и `to_phase_id` ссылаются на `RecipeRevisionPhase` (шаблоны), а не на `GrowCyclePhase` (снапшоты)
   - Это может быть проблемой для отслеживания переходов между снапшотами в конкретном цикле
   - Возможно, нужно добавить дополнительные поля для ссылок на снапшоты или изменить логику

## 🔧 Рекомендации

1. **Удалить legacy модели:**
   - Заменить все использования `ZoneRecipeInstance` на `GrowCycle`
   - Заменить все использования `PlantCycle` на `GrowCycle`
   - Заменить все использования `ZoneCycle` на `GrowCycle`
   - Удалить модели `ZoneRecipeInstance`, `PlantCycle`, `ZoneCycle`

2. **Проверить логику `GrowCycleTransition`:**
   - Рассмотреть добавление полей `from_grow_cycle_phase_id` и `to_grow_cycle_phase_id` для ссылок на снапшоты
   - Или оставить текущую логику, если ссылки на шаблоны достаточны для истории переходов

