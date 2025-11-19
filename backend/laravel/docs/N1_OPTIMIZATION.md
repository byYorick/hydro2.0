# N+1 Query Optimization Documentation

Этот документ описывает оптимизацию N+1 запросов в Laravel приложении.

## Проблема N+1 запросов

N+1 проблема возникает, когда:
1. Загружается коллекция моделей (1 запрос)
2. Для каждой модели выполняется отдельный запрос для загрузки связанных данных (N запросов)

**Пример проблемы:**
```php
$zones = Zone::all(); // 1 запрос
foreach ($zones as $zone) {
    echo $zone->greenhouse->name; // N запросов (по одному на каждую зону)
}
```

## Решение: Eager Loading

Используйте `with()` для предварительной загрузки связанных данных:

```php
$zones = Zone::with('greenhouse')->get(); // 2 запроса (zones + greenhouses)
foreach ($zones as $zone) {
    echo $zone->greenhouse->name; // Без дополнительных запросов
}
```

## Оптимизированные места

### 1. ZoneController

**index()** - список зон:
```php
Zone::query()
    ->withCount('nodes')
    ->with(['greenhouse:id,name', 'preset:id,name'])
    ->paginate(25);
```

**show()** - детали зоны:
```php
$zone->load(['greenhouse', 'preset', 'nodes', 'recipeInstance.recipe.phases']);
```

**health()** - здоровье зоны:
```php
$zone->load([
    'greenhouse', 
    'preset', 
    'nodes' => function ($query) {
        $query->select('id', 'zone_id', 'status');
    },
    'recipeInstance.recipe.phases',
    'alerts' => function ($query) {
        $query->where('status', 'ACTIVE')->select('id', 'zone_id', 'status');
    }
]);
```

### 2. NodeController

**index()** - список узлов:
```php
DeviceNode::query()
    ->with(['zone:id,name,status', 'channels'])
    ->paginate(25);
```

### 3. AlertController

**index()** - список алертов:
```php
Alert::query()
    ->with(['zone:id,name,status'])
    ->latest('created_at')
    ->paginate(25);
```

### 4. ZoneService

**changePhase()** - изменение фазы:
```php
$instance = $zone->load('recipeInstance.recipe.phases')->recipeInstance;
// Используем $recipe->phases вместо $recipe->phases()
```

**nextPhase()** - следующая фаза:
```php
$instance = $zone->load('recipeInstance.recipe.phases')->recipeInstance;
// Используем $recipe->phases вместо $recipe->phases()
```

### 5. ReportController

**zoneHarvests()** - урожаи зоны:
```php
Harvest::where('zone_id', $zone->id)
    ->with(['recipe:id,name'])
    ->paginate(25);
```

## Оптимизация полей

Используйте селекцию полей для уменьшения объема данных:

```php
// Загружаем только нужные поля
->with(['zone:id,name,status'])
```

**Важно:** При использовании селекции полей, всегда включайте:
- `id` (для связи)
- Foreign key поля (если используются)

## Вложенные отношения

Для вложенных отношений используйте точечную нотацию:

```php
// Загрузка вложенных отношений
->with(['recipeInstance.recipe.phases'])

// Это загрузит:
// - recipeInstance
// - recipe (через recipeInstance)
// - phases (через recipe)
```

## Мониторинг N+1 запросов

### Laravel Debugbar

Установите `barryvdh/laravel-debugbar` для отслеживания запросов:

```bash
composer require barryvdh/laravel-debugbar --dev
```

### Логирование запросов

Включите логирование всех SQL запросов:

```php
// config/database.php
'connections' => [
    'pgsql' => [
        // ...
        'log_queries' => env('DB_LOG_QUERIES', false),
    ],
],
```

### Laravel Telescope

Используйте Laravel Telescope для мониторинга запросов:

```bash
composer require laravel/telescope --dev
php artisan telescope:install
```

## Best Practices

1. **Всегда используйте eager loading** при работе с коллекциями
2. **Селекция полей** для уменьшения объема данных
3. **Проверяйте запросы** через Debugbar или Telescope
4. **Используйте `withCount()`** для подсчета связанных записей
5. **Избегайте lazy loading** в циклах

## Примеры анти-паттернов

### ❌ Плохо: Lazy Loading в цикле

```php
$zones = Zone::all();
foreach ($zones as $zone) {
    echo $zone->greenhouse->name; // N+1 запрос
}
```

### ✅ Хорошо: Eager Loading

```php
$zones = Zone::with('greenhouse')->get();
foreach ($zones as $zone) {
    echo $zone->greenhouse->name; // Без дополнительных запросов
}
```

### ❌ Плохо: Запросы в отношениях

```php
$zone = Zone::find(1);
$maxPhase = $zone->recipeInstance->recipe->phases()->max('phase_index'); // Дополнительный запрос
```

### ✅ Хорошо: Использование загруженных данных

```php
$zone = Zone::with('recipeInstance.recipe.phases')->find(1);
$maxPhase = $zone->recipeInstance->recipe->phases->max('phase_index'); // Используем коллекцию
```

## Проверка оптимизации

### До оптимизации

```sql
-- 1 запрос для зон
SELECT * FROM zones;

-- N запросов для greenhouse (по одному на каждую зону)
SELECT * FROM greenhouses WHERE id = 1;
SELECT * FROM greenhouses WHERE id = 2;
-- ...
```

### После оптимизации

```sql
-- 1 запрос для зон
SELECT * FROM zones;

-- 1 запрос для всех greenhouses
SELECT id, name FROM greenhouses WHERE id IN (1, 2, 3, ...);
```

## Миграция

Оптимизация выполнена в следующих файлах:
- `app/Http/Controllers/ZoneController.php`
- `app/Http/Controllers/NodeController.php`
- `app/Http/Controllers/AlertController.php`
- `app/Services/ZoneService.php`
- `app/Http/Controllers/ReportController.php`

---

**Дата создания:** 2025-01-27  
**Версия:** 1.0

