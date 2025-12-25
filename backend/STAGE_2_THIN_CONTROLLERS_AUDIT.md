# Аудит Этапа 2 на соответствие принципу тонких контроллеров

Дата: 2025-12-25

## Нарушения принципа тонких контроллеров

### ❌ GrowCycleController

#### Метод `store()` - КРИТИЧЕСКОЕ НАРУШЕНИЕ
- **Проблема**: Прямая работа с БД в контроллере
- **Нарушения**:
  - `DB::transaction()` в контроллере
  - `GrowCycle::create()` напрямую
  - `GrowCycleTransition::create()` напрямую
  - `DB::table('zone_events')->insert()` напрямую
  - `broadcast()` в контроллере
- **Должно быть**: Вызов `GrowCycleService::createCycle()`

#### Метод `advancePhase()` - КРИТИЧЕСКОЕ НАРУШЕНИЕ
- **Проблема**: Вся бизнес-логика в контроллере
- **Нарушения**:
  - Поиск следующей фазы в контроллере
  - `DB::transaction()` в контроллере
  - `$growCycle->update()` напрямую
  - `GrowCycleTransition::create()` напрямую
  - `DB::table('zone_events')->insert()` напрямую
  - `broadcast()` в контроллере
- **Должно быть**: Вызов `GrowCycleService::advancePhase()`

#### Метод `setPhase()` - КРИТИЧЕСКОЕ НАРУШЕНИЕ
- **Проблема**: Вся бизнес-логика в контроллере
- **Нарушения**:
  - Поиск фазы в контроллере
  - `DB::transaction()` в контроллере
  - `$growCycle->update()` напрямую
  - `GrowCycleTransition::create()` напрямую
  - `DB::table('zone_events')->insert()` напрямую
  - `broadcast()` в контроллере
- **Должно быть**: Вызов `GrowCycleService::setPhase()`

#### Метод `changeRecipeRevision()` - КРИТИЧЕСКОЕ НАРУШЕНИЕ
- **Проблема**: Вся бизнес-логика в контроллере
- **Нарушения**:
  - Логика применения ревизии в контроллере
  - `DB::transaction()` в контроллере
  - `$growCycle->update()` напрямую
  - `GrowCycleTransition::create()` напрямую
  - `DB::table('zone_events')->insert()` напрямую
  - `broadcast()` в контроллере
- **Должно быть**: Вызов `GrowCycleService::changeRecipeRevision()`

#### Метод `pause()` - НАРУШЕНИЕ
- **Проблема**: Прямая работа с БД
- **Нарушения**:
  - `$growCycle->update()` напрямую
  - `DB::table('zone_events')->insert()` напрямую
  - `broadcast()` в контроллере
- **Должно быть**: Вызов `GrowCycleService::pause()`

#### Метод `resume()` - НАРУШЕНИЕ
- **Проблема**: Прямая работа с БД
- **Нарушения**:
  - `$growCycle->update()` напрямую
  - `DB::table('zone_events')->insert()` напрямую
  - `broadcast()` в контроллере
- **Должно быть**: Вызов `GrowCycleService::resume()`

#### Метод `harvest()` - НАРУШЕНИЕ
- **Проблема**: Прямая работа с БД
- **Нарушения**:
  - `DB::transaction()` в контроллере
  - `$growCycle->update()` напрямую
  - `DB::table('zone_events')->insert()` напрямую
  - `broadcast()` в контроллере
- **Должно быть**: Вызов `GrowCycleService::harvest()`

#### Метод `abort()` - НАРУШЕНИЕ
- **Проблема**: Прямая работа с БД
- **Нарушения**:
  - `DB::transaction()` в контроллере
  - `$growCycle->update()` напрямую
  - `DB::table('zone_events')->insert()` напрямую
  - `broadcast()` в контроллере
- **Должно быть**: Вызов `GrowCycleService::abort()`

#### Метод `indexByGreenhouse()` - НАРУШЕНИЕ
- **Проблема**: Прямой запрос к БД
- **Нарушения**:
  - `GrowCycle::where()->with()->orderBy()->paginate()` в контроллере
- **Должно быть**: Вызов `GrowCycleService::getByGreenhouse()`

### ❌ RecipeRevisionController

#### Метод `store()` - КРИТИЧЕСКОЕ НАРУШЕНИЕ
- **Проблема**: Вся бизнес-логика клонирования в контроллере
- **Нарушения**:
  - `DB::transaction()` в контроллере
  - Определение номера ревизии в контроллере
  - Логика клонирования фаз и шагов в контроллере
  - `RecipeRevision::create()` напрямую
  - `$newPhase->steps()->create()` напрямую
- **Должно быть**: Вызов `RecipeRevisionService::createRevision()` или `RecipeRevisionService::cloneRevision()`

#### Метод `update()` - НАРУШЕНИЕ
- **Проблема**: Прямое обновление модели
- **Нарушения**:
  - `$recipeRevision->update()` напрямую
- **Должно быть**: Вызов `RecipeRevisionService::updateRevision()`

#### Метод `publish()` - НАРУШЕНИЕ
- **Проблема**: Бизнес-логика валидации в контроллере
- **Нарушения**:
  - Проверка количества фаз в контроллере
  - `$recipeRevision->update()` напрямую
- **Должно быть**: Вызов `RecipeRevisionService::publishRevision()`

### ❌ RecipeRevisionPhaseController

#### Метод `store()` - НАРУШЕНИЕ
- **Проблема**: Бизнес-логика определения индекса в контроллере
- **Нарушения**:
  - Определение `phase_index` в контроллере
  - `$recipeRevision->phases()->create()` напрямую
- **Должно быть**: Вызов `RecipeRevisionPhaseService::createPhase()`

#### Метод `update()` - НАРУШЕНИЕ
- **Проблема**: Прямое обновление модели
- **Нарушения**:
  - `$recipeRevisionPhase->update()` напрямую
- **Должно быть**: Вызов `RecipeRevisionPhaseService::updatePhase()`

#### Метод `destroy()` - НАРУШЕНИЕ
- **Проблема**: Прямое удаление модели
- **Нарушения**:
  - `$recipeRevisionPhase->delete()` напрямую
- **Должно быть**: Вызов `RecipeRevisionPhaseService::deletePhase()`

### ✅ InfrastructureInstanceController

#### Метод `store()` - НАРУШЕНИЕ
- **Проблема**: Прямое создание модели
- **Нарушения**:
  - `InfrastructureInstance::create()` напрямую
- **Должно быть**: Вызов `InfrastructureInstanceService::create()`

#### Метод `update()` - НАРУШЕНИЕ
- **Проблема**: Прямое обновление модели
- **Нарушения**:
  - `$infrastructureInstance->update()` напрямую
- **Должно быть**: Вызов `InfrastructureInstanceService::update()`

#### Метод `destroy()` - НАРУШЕНИЕ
- **Проблема**: Прямое удаление модели
- **Нарушения**:
  - `$infrastructureInstance->delete()` напрямую
- **Должно быть**: Вызов `InfrastructureInstanceService::delete()`

#### Метод `indexForZone()` - НАРУШЕНИЕ
- **Проблема**: Прямой запрос к БД
- **Нарушения**:
  - `InfrastructureInstance::where()->with()->get()` в контроллере
- **Должно быть**: Вызов `InfrastructureInstanceService::getForZone()`

#### Метод `indexForGreenhouse()` - НАРУШЕНИЕ
- **Проблема**: Прямой запрос к БД
- **Нарушения**:
  - `InfrastructureInstance::where()->with()->get()` в контроллере
- **Должно быть**: Вызов `InfrastructureInstanceService::getForGreenhouse()`

### ✅ ChannelBindingController

#### Метод `store()` - НАРУШЕНИЕ
- **Проблема**: Прямое создание модели
- **Нарушения**:
  - `ChannelBinding::create()` напрямую
- **Должно быть**: Вызов `ChannelBindingService::create()`

#### Метод `update()` - НАРУШЕНИЕ
- **Проблема**: Прямое обновление модели
- **Нарушения**:
  - `$channelBinding->update()` напрямую
- **Должно быть**: Вызов `ChannelBindingService::update()`

#### Метод `destroy()` - НАРУШЕНИЕ
- **Проблема**: Прямое удаление модели
- **Нарушения**:
  - `$channelBinding->delete()` напрямую
- **Должно быть**: Вызов `ChannelBindingService::delete()`

## Статистика нарушений

- **Критические нарушения**: 5 методов
- **Нарушения**: 20+ методов
- **Контроллеров с нарушениями**: 5 из 5 (100%)

## Рекомендации

1. **Создать сервисы**:
   - `GrowCycleService` (расширить существующий)
   - `RecipeRevisionService` (новый)
   - `RecipeRevisionPhaseService` (новый)
   - `InfrastructureInstanceService` (новый)
   - `ChannelBindingService` (новый)

2. **Рефакторинг контроллеров**:
   - Вынести всю бизнес-логику в сервисы
   - Оставить в контроллерах только HTTP-логику
   - Убрать все `DB::transaction()`, `DB::table()`, прямые операции с моделями

3. **Приоритет рефакторинга**:
   - Высокий: `GrowCycleController` (критические нарушения)
   - Средний: `RecipeRevisionController` (критические нарушения)
   - Низкий: Остальные контроллеры (простые CRUD операции)

