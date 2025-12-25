# Прогресс удаления legacy кода Этапа 2

Дата: 2025-12-25

## ✅ Выполнено

### 1. Удален неиспользуемый импорт
- ✅ `ZoneRecipeInstance` из `GrowCycleService.php` - удален (не использовался)

### 2. Заменен `ZoneCycle` на `GrowCycle` в `ZoneCommandController`
- ✅ Проверка активного цикла теперь использует `GrowCycle` с правильными статусами
- ✅ Обновление циклов теперь использует `GrowCycle` вместо `ZoneCycle`
- ✅ Добавлено предупреждение о том, что создание циклов должно происходить через `GrowCycleController::store()`

## ⏳ Осталось заменить

### `ZoneRecipeInstance` используется в:
1. `app/Models/Zone.php` - метод `recipeInstance()` помечен как @deprecated
2. `app/Services/ZoneService.php` - методы `attachRecipe()`, `changePhase()`, `nextPhase()`
3. `app/Services/RecipeService.php` - методы используют legacy модель
4. `app/Services/RecipeAnalyticsService.php` - использует для аналитики
5. `app/Http/Controllers/GrowCycleWizardController.php` - использует legacy модель
6. `app/Http/Controllers/ZoneController.php` - импорт
7. `app/Http/Controllers/SimulationController.php` - использует
8. `app/Models/Recipe.php` - relationship `zoneRecipeInstances()`
9. `app/Jobs/CalculateRecipeAnalyticsJob.php` - использует
10. `app/Console/Commands/FixZone6Command.php` - использует

### `PlantCycle` используется в:
1. `app/Models/Plant.php` - relationship `cycles()` → `PlantCycle`
2. `app/Models/PlantCycle.php` - модель существует

### `ZoneCycle` используется в:
- ✅ **ЗАМЕНЕН** в `ZoneCommandController`

## 📝 Рекомендации

1. **ZoneService методы** (`attachRecipe`, `changePhase`, `nextPhase`):
   - Эти методы должны быть заменены на использование `GrowCycleService`
   - Или помечены как @deprecated с указанием использовать новые методы

2. **RecipeService методы**:
   - `applyToZone()` должен использовать `GrowCycleService::createCycle()`
   - `getActiveInstancesCount()` должен использовать `GrowCycle::query()->whereIn('status', ...)`

3. **RecipeAnalyticsService**:
   - Должен использовать `GrowCycle` вместо `ZoneRecipeInstance`
   - Аналитика должна быть привязана к циклам, а не к экземплярам рецептов

4. **GrowCycleWizardController**:
   - Должен использовать `GrowCycleService::createCycle()` вместо создания `ZoneRecipeInstance`

5. **Plant.cycles()** relationship:
   - Должен быть заменен на `GrowCycle::where('plant_id', $this->id)`
   - Или удален, если не используется

## 🔧 Следующие шаги

1. Заменить методы в `ZoneService` на использование `GrowCycleService`
2. Заменить методы в `RecipeService` на использование `GrowCycleService`
3. Обновить `RecipeAnalyticsService` для работы с `GrowCycle`
4. Обновить `GrowCycleWizardController` для использования новых методов
5. Удалить модели `ZoneRecipeInstance`, `PlantCycle`, `ZoneCycle` после замены всех использований

