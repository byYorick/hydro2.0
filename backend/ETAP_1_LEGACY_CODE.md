# Этап 1 - Обнаруженный legacy код

Дата: 2025-12-25

## ⚠️ Обнаруженные упоминания legacy кода

### 1. Модель ZoneRecipeInstance
**Файл:** `backend/laravel/app/Models/ZoneRecipeInstance.php`
**Статус:** Модель существует, но таблица удалена
**Действие:** Требуется удалить модель или пометить как deprecated

### 2. Упоминания в коде
Найдены упоминания `zone_recipe_instance` в следующих файлах:
- `backend/laravel/app/Models/Zone.php`
- `backend/laravel/app/Services/GrowCycleService.php`
- `backend/laravel/app/Models/Recipe.php`
- `backend/laravel/app/Http/Controllers/ZoneController.php`
- `backend/laravel/app/Services/ZoneService.php`
- `backend/laravel/app/Http/Controllers/GrowCycleWizardController.php`
- `backend/laravel/app/Http/Controllers/SimulationController.php`
- `backend/laravel/app/Services/RecipeService.php`
- `backend/laravel/app/Services/RecipeAnalyticsService.php`
- `backend/laravel/app/Jobs/CalculateRecipeAnalyticsJob.php`
- `backend/laravel/app/Console/Commands/FixZone6Command.php`

**Рекомендация:** Проверить каждый файл и удалить или заменить legacy код на новую модель `GrowCycle`.

## 📋 План действий

1. ✅ Удалить модель `ZoneRecipeInstance.php` (таблица уже удалена)
2. ⏳ Проверить и обновить все упоминания в сервисах и контроллерах
3. ⏳ Удалить legacy методы из моделей (если есть)
4. ⏳ Обновить тесты (если используют legacy код)

**Приоритет:** Средний (код может работать, но ссылается на несуществующую таблицу)

