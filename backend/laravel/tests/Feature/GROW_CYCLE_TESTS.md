# Тесты для системы стадий выращивания (Grow Cycles)

## Структура тестов

### Feature тесты

1. **GrowCycleServiceTest** - тесты сервиса работы с циклами
   - `it_creates_a_grow_cycle` - создание цикла
   - `it_starts_a_cycle` - запуск цикла
   - `it_computes_expected_harvest` - вычисление даты сбора
   - `it_advances_stage_automatically` - автоматический переход стадии
   - `it_advances_to_specific_stage` - ручной переход на конкретную стадию

2. **GrowCycleControllerTest** - тесты API контроллера
   - `it_creates_a_grow_cycle` - POST /api/zones/{zone}/grow-cycles
   - `it_creates_and_starts_cycle_immediately` - создание и запуск цикла
   - `it_gets_active_cycle_with_dto` - GET /api/zones/{zone}/grow-cycle
   - `it_advances_stage` - POST /api/grow-cycles/{id}/advance-phase
   - `it_pauses_a_cycle` - POST /api/grow-cycles/{id}/pause
   - `it_resumes_a_cycle` - POST /api/grow-cycles/{id}/resume
   - `it_harvests_a_cycle` - POST /api/grow-cycles/{id}/harvest
   - `it_aborts_a_cycle` - POST /api/grow-cycles/{id}/abort
   - `it_requires_authentication` - проверка аутентификации

3. **RecipeStageMapControllerTest** - тесты stage-map метаданных рецепта
   - `it_gets_stage_map_for_recipe` - GET /api/recipes/{id}/stage-map
   - `it_auto_creates_stage_map_if_not_exists` - автоматическое создание
   - `it_updates_stage_map` - PUT /api/recipes/{id}/stage-map
   - `it_requires_operator_role_to_update` - проверка прав доступа
   - `it_validates_stage_map_data` - валидация данных

### Unit тесты

1. **GrowStageTemplateTest** - тесты модели шаблонов стадий
   - `it_has_recipe_phase_relationship` - проверка связи
   - `it_casts_ui_meta_to_array` - проверка cast'ов

2. **RecipeRevisionPhaseTest** - тесты фаз ревизии
   - `it_belongs_to_revision` - связь с ревизией
   - `it_belongs_to_stage_template` - связь с шаблоном
   - `it_casts_extensions_to_array` - cast extensions
   - `it_appends_targets_attribute` - targets accessor

## Фабрики

Созданы фабрики для всех новых моделей:
- `GrowCycleFactory` - с состояниями running, paused, harvested
- `GrowStageTemplateFactory` - с методами planting, veg, flower
- `RecipeRevisionPhaseFactory` - для создания фаз ревизий

## Запуск тестов

```bash
# Все тесты для grow cycles
php artisan test --filter=GrowCycle

# Тесты сервиса
php artisan test tests/Feature/GrowCycleServiceTest.php

# Тесты контроллера
php artisan test tests/Feature/GrowCycleControllerTest.php

# Тесты stage-map
php artisan test tests/Feature/RecipeStageMapControllerTest.php

# Unit тесты
php artisan test tests/Unit/GrowStageTemplateTest.php
php artisan test tests/Unit/RecipeStageMapTest.php
```

## Покрытие

Тесты покрывают:
- ✅ Создание и управление циклами
- ✅ Переходы между стадиями
- ✅ Вычисление прогресса и дат
- ✅ API endpoints
- ✅ Валидация и права доступа
- ✅ Связи моделей
