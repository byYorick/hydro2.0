# Этап 2.1: Проверка Eloquent моделей

**Дата:** 2025-12-25  
**Статус:** ✅ Проверка завершена

## Результаты проверки

### ✅ Синтаксис моделей
- Все модели успешно инстанцируются
- Нет ошибок линтера
- PHP синтаксис корректен

### ✅ Связи моделей

#### RecipeRevision
- ✅ `belongsTo(Recipe::class)` - связь с рецептом
- ✅ `belongsTo(User::class, 'created_by')` - создатель ревизии
- ✅ `hasMany(RecipeRevisionPhase::class)` - фазы ревизии
- ✅ `hasMany(GrowCycle::class)` - циклы, использующие ревизию

#### RecipeRevisionPhase
- ✅ `belongsTo(RecipeRevision::class)` - ревизия рецепта
- ✅ `belongsTo(GrowStageTemplate::class)` - шаблон стадии для UI
- ✅ `hasMany(RecipeRevisionPhaseStep::class)` - подшаги
- ✅ `hasMany(GrowCycle::class, 'current_phase_id')` - циклы в этой фазе
- ✅ `hasMany(GrowCycleTransition::class, 'from_phase_id')` - переходы из фазы
- ✅ `hasMany(GrowCycleTransition::class, 'to_phase_id')` - переходы в фазу

#### GrowCycle
- ✅ `belongsTo(Greenhouse::class)` - теплица
- ✅ `belongsTo(Zone::class)` - зона
- ✅ `belongsTo(Plant::class)` - растение
- ✅ `belongsTo(Recipe::class)` - рецепт (legacy, для совместимости)
- ✅ `belongsTo(RecipeRevision::class)` - ревизия рецепта (центр истины)
- ✅ `belongsTo(RecipeRevisionPhase::class, 'current_phase_id')` - текущая фаза
- ✅ `belongsTo(RecipeRevisionPhaseStep::class, 'current_step_id')` - текущий подшаг
- ✅ `hasMany(GrowCycleOverride::class)` - перекрытия параметров
- ✅ `hasMany(GrowCycleTransition::class)` - история переходов

#### Zone
- ✅ `hasOne(GrowCycle::class)` с фильтром по статусу - активный цикл
- ✅ `morphMany(InfrastructureInstance::class, 'owner')` - инфраструктура зоны
- ✅ `hasManyThrough(ChannelBinding::class, InfrastructureInstance::class)` - привязки каналов

#### InfrastructureInstance
- ✅ `morphTo()` - полиморфная связь с владельцем (zone|greenhouse)
- ✅ `hasMany(ChannelBinding::class)` - привязки каналов

### ✅ Типы данных и casts

#### RecipeRevisionPhase
- ✅ Все числовые поля с правильной точностью (decimal:2, decimal:5, etc)
- ✅ `lighting_start_time` cast в datetime
- ✅ `extensions` cast в array

#### GrowCycle
- ✅ `status` cast в enum GrowCycleStatus
- ✅ Все timestamp поля cast в datetime
- ✅ `settings` и `progress_meta` cast в array

#### GrowCycleOverride
- ✅ `applies_from` и `applies_until` cast в datetime
- ✅ `is_active` cast в boolean

### ✅ Методы моделей

#### RecipeRevision
- ✅ `isPublished()` - проверка статуса PUBLISHED
- ✅ `isDraft()` - проверка статуса DRAFT

#### GrowCycle
- ✅ `isActive()` - проверка активного статуса
- ✅ `scopeActive()` - scope для активных циклов
- ✅ `scopeForZone()` - scope для циклов зоны
- ✅ `activeOverrides()` - активные перекрытия

#### GrowCycleOverride
- ✅ `isCurrentlyActive()` - проверка активности с учетом времени
- ✅ `getTypedValue()` - получение значения с правильным типом

#### InfrastructureInstance
- ✅ `scopeForZone()` - фильтр по зоне
- ✅ `scopeForGreenhouse()` - фильтр по теплице
- ✅ `scopeOfType()` - фильтр по типу оборудования

#### ChannelBinding
- ✅ `scopeActuators()` - фильтр актуаторов
- ✅ `scopeSensors()` - фильтр сенсоров
- ✅ `scopeWithRole()` - фильтр по роли

### ✅ Соответствие плану рефакторинга

#### Требование: `Zone::with('activeGrowCycle.currentPhase')` работает
- ✅ Метод `activeGrowCycle()` определен в Zone
- ✅ Метод `currentPhase()` определен в GrowCycle
- ✅ Связи настроены корректно

#### Центр истины = GrowCycle
- ✅ GrowCycle имеет связь с RecipeRevision (не Recipe напрямую)
- ✅ GrowCycle имеет current_phase_id и current_step_id
- ✅ GrowCycle имеет overrides и transitions

#### Ревизии рецептов
- ✅ RecipeRevision связан с Recipe
- ✅ RecipeRevision имеет статусы DRAFT|PUBLISHED|ARCHIVED
- ✅ RecipeRevision имеет phases с упорядочиванием по phase_index

#### Полиморфная инфраструктура
- ✅ InfrastructureInstance имеет owner_type и owner_id
- ✅ Zone и Greenhouse имеют связи с InfrastructureInstance
- ✅ ChannelBinding связан с InfrastructureInstance (не напрямую с Zone)

### ⚠️ Замечания

1. **Legacy методы помечены как @deprecated**
   - `Recipe::phases()`, `Recipe::zoneRecipeInstances()`, `Recipe::stageMaps()`
   - `Zone::recipeInstance()`, `Zone::infrastructure()`, `Zone::legacyChannelBindings()`
   - Эти методы будут удалены после полного перехода на новую модель

2. **recipe_id в GrowCycle оставлено**
   - По плану можно удалить после полного перехода
   - Пока оставлено для совместимости

3. **recipe_revision_id пока nullable**
   - По плану должно стать NOT NULL после миграции данных
   - Требуется заполнение данных из legacy таблиц

### ✅ Готово к Этапу 2.2

Все модели проверены и соответствуют плану рефакторинга. Можно переходить к созданию EffectiveTargetsService.

---

## Проверенные файлы

### Новые модели:
- ✅ `app/Models/RecipeRevision.php`
- ✅ `app/Models/RecipeRevisionPhase.php`
- ✅ `app/Models/RecipeRevisionPhaseStep.php`
- ✅ `app/Models/GrowCycleOverride.php`
- ✅ `app/Models/GrowCycleTransition.php`
- ✅ `app/Models/InfrastructureInstance.php`
- ✅ `app/Models/ChannelBinding.php`

### Обновленные модели:
- ✅ `app/Models/GrowCycle.php`
- ✅ `app/Models/Recipe.php`
- ✅ `app/Models/Zone.php`
- ✅ `app/Models/Greenhouse.php`

