# Отчет о реализации Этапа 2.4 - Права доступа

Дата: 2025-12-25

## ✅ Выполнено

### Созданы Policy классы

1. **GrowCyclePolicy** (`app/Policies/GrowCyclePolicy.php`):
   - `manage()` - проверка прав на управление циклами
   - `create()` - проверка прав на создание циклов
   - `update()` - проверка прав на обновление циклов (pause, resume, harvest, abort)
   - `view()` - просмотр доступен всем авторизованным пользователям
   - `switchPhase()` - проверка прав на переключение фаз
   - `changeRecipeRevision()` - проверка прав на смену ревизии рецепта

2. **RecipeRevisionPolicy** (`app/Policies/RecipeRevisionPolicy.php`):
   - `manage()` - проверка прав на управление ревизиями
   - `create()` - проверка прав на создание ревизий
   - `update()` - проверка прав на редактирование (только DRAFT)
   - `publish()` - проверка прав на публикацию (только DRAFT)
   - `view()` - просмотр доступен всем авторизованным пользователям

### Создан AuthServiceProvider

- Зарегистрирован в `bootstrap/app.php`
- Зарегистрированы Policy для `GrowCycle` и `RecipeRevision`

### Расширена модель User

- Добавлен метод `hasRole(string $role): bool`
- Добавлен метод `isAgronomist(): bool`

### Добавлены проверки прав в контроллеры

#### GrowCycleController
- ✅ `store()` - проверка `Gate::allows('create', [GrowCycle::class, $zone])`
- ✅ `pause()` - проверка `Gate::allows('update', $growCycle)`
- ✅ `resume()` - проверка `Gate::allows('update', $growCycle)`
- ✅ `harvest()` - проверка `Gate::allows('update', $growCycle)`
- ✅ `abort()` - проверка `Gate::allows('update', $growCycle)`
- ✅ `advancePhase()` - проверка `Gate::allows('switchPhase', $growCycle)`
- ✅ `setPhase()` - проверка `Gate::allows('switchPhase', $growCycle)`
- ✅ `changeRecipeRevision()` - проверка `Gate::allows('changeRecipeRevision', $growCycle)`

#### RecipeRevisionController
- ✅ `store()` - проверка `Gate::allows('create', RecipeRevision::class)`
- ✅ `update()` - проверка `Gate::allows('update', $recipeRevision)`
- ✅ `publish()` - проверка `Gate::allows('publish', $recipeRevision)`

## Правила доступа

### Роль `agronomist` может:
- ✅ Создавать циклы выращивания
- ✅ Управлять циклами (pause, resume, harvest, abort)
- ✅ Переключать фазы (advance, manual switch)
- ✅ Менять ревизию рецепта в цикле
- ✅ Создавать ревизии рецептов
- ✅ Редактировать ревизии рецептов (только DRAFT)
- ✅ Публиковать ревизии рецептов (только DRAFT)

### Остальные роли могут:
- ✅ Просматривать циклы (read-only)
- ✅ Просматривать ревизии рецептов (read-only)
- ✅ Выполнять внецикловые команды (по отдельной политике, если нужно)

## Статистика

- **Policy классов создано**: 2
- **Методов проверки прав**: 11
- **Методов контроллеров защищено**: 11
- **Роль с полными правами**: `agronomist`

## Результат

✅ **Этап 2.4 выполнен успешно**

Все методы управления циклами и рецептами защищены проверками прав. Только пользователи с ролью `agronomist` могут выполнять операции управления. Остальные пользователи имеют read-only доступ.

