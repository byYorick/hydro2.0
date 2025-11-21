<?php

/**
 * Скрипт для проверки зоны 6 и привязки рецепта
 * Запуск: php check_zone6.php [recipe_id]
 */

require __DIR__ . '/vendor/autoload.php';

$app = require_once __DIR__ . '/bootstrap/app.php';
$app->make(\Illuminate\Contracts\Console\Kernel::class)->bootstrap();

use App\Models\Zone;
use App\Models\Recipe;
use App\Models\ZoneRecipeInstance;
use App\Services\ZoneService;
use Illuminate\Support\Facades\Cache;

echo "🔍 Проверка зоны 6...\n";

// Проверяем зону 6
$zone = Zone::find(6);

if (!$zone) {
    echo "❌ Зона 6 не найдена в базе данных!\n";
    exit(1);
}

echo "✅ Зона 6 найдена: {$zone->name}\n";
echo "   ID: {$zone->id}\n";
echo "   Статус: {$zone->status}\n";
echo "   Теплица ID: " . ($zone->greenhouse_id ?? 'не указана') . "\n";
echo "   Описание: " . ($zone->description ?? 'нет') . "\n";

// Проверяем рецепт
$recipeInstance = $zone->recipeInstance;
if ($recipeInstance) {
    $recipe = $recipeInstance->recipe;
    echo "✅ Рецепт привязан: ID {$recipeInstance->recipe_id} - {$recipe->name}\n";
    echo "   Текущая фаза: " . ($recipeInstance->current_phase_index ?? 0) . "\n";
} else {
    echo "⚠️  Рецепт не привязан к зоне 6\n";
}

echo "\n";
echo "🔍 Проверка видимости на фронте...\n";

// Очищаем кеш для всех пользователей
echo "   Очистка кеша зон...\n";
for ($i = 1; $i <= 100; $i++) {
    Cache::forget("zones_list_{$i}");
    Cache::forget("dashboard_data_{$i}");
}
Cache::forget('zones_list');
Cache::forget('dashboard_data');
echo "   ✅ Кеш очищен\n";

// Проверяем, есть ли зона в базе при обычном запросе
$zonesQuery = Zone::query()
    ->select(['id','name','status','description','greenhouse_id'])
    ->get();

$zoneInQuery = $zonesQuery->firstWhere('id', 6);
if ($zoneInQuery) {
    echo "✅ Зона 6 возвращается при обычном запросе из БД\n";
} else {
    echo "❌ Зона 6 НЕ возвращается при запросе из БД!\n";
}

// Список рецептов
echo "\n";
echo "📋 Доступные рецепты:\n";
$recipes = Recipe::all(['id', 'name', 'description']);
if ($recipes->isEmpty()) {
    echo "   Рецептов не найдено\n";
} else {
    foreach ($recipes as $recipe) {
        $phasesCount = $recipe->phases()->count();
        echo "   ID {$recipe->id}: {$recipe->name} ({$phasesCount} фаз)\n";
        if ($recipe->description) {
            echo "      Описание: {$recipe->description}\n";
        }
    }
}

// Привязка рецепта, если указан аргумент
if (isset($argv[1]) && is_numeric($argv[1])) {
    $recipeId = (int)$argv[1];
    echo "\n";
    echo "🔗 Привязка рецепта ID {$recipeId} к зоне 6...\n";
    
    $recipe = Recipe::find($recipeId);
    if (!$recipe) {
        echo "❌ Рецепт ID {$recipeId} не найден!\n";
        exit(1);
    }
    
    // Проверяем наличие фаз
    $phasesCount = $recipe->phases()->count();
    if ($phasesCount === 0) {
        echo "⚠️  Внимание: рецепт '{$recipe->name}' не имеет фаз!\n";
    }
    
    try {
        $zoneService = app(ZoneService::class);
        $newInstance = $zoneService->attachRecipe($zone, $recipeId, now());
        
        echo "✅ Рецепт '{$recipe->name}' успешно привязан к зоне 6!\n";
        echo "   Instance ID: {$newInstance->id}\n";
        echo "   Текущая фаза: 0 (первая фаза)\n";
        
        // Очищаем кеш еще раз
        for ($i = 1; $i <= 100; $i++) {
            Cache::forget("zones_list_{$i}");
            Cache::forget("dashboard_data_{$i}");
        }
        Cache::forget('zones_list');
        Cache::forget('dashboard_data');
        echo "   ✅ Кеш очищен\n";
        
    } catch (\Exception $e) {
        echo "❌ Ошибка при привязке рецепта: {$e->getMessage()}\n";
        exit(1);
    }
} else {
    echo "\n";
    echo "💡 Для привязки рецепта используйте: php check_zone6.php RECIPE_ID\n";
}

echo "\n";
echo "✅ Проверка завершена\n";

