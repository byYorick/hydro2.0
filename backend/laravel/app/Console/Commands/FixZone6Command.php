<?php

namespace App\Console\Commands;

use App\Models\Zone;
use App\Models\Recipe;
use App\Models\ZoneRecipeInstance;
use App\Services\ZoneService;
use Illuminate\Console\Command;
use Illuminate\Support\Facades\Cache;
use Illuminate\Support\Facades\DB;

class FixZone6Command extends Command
{
    protected $signature = 'zone:fix-6 {--attach-recipe= : Recipe ID to attach} {--list-recipes : List available recipes}';
    protected $description = 'Проверить и исправить проблемы с зоной 6';

    public function handle(ZoneService $zoneService)
    {
        $this->info('🔍 Проверка зоны 6...');
        
        // Проверяем зону 6
        $zone = Zone::find(6);
        
        if (!$zone) {
            $this->error('❌ Зона 6 не найдена в базе данных!');
            return 1;
        }
        
        $this->info("✅ Зона 6 найдена: {$zone->name}");
        $this->line("   ID: {$zone->id}");
        $this->line("   Статус: {$zone->status}");
        $this->line("   Теплица ID: " . ($zone->greenhouse_id ?? 'не указана'));
        $this->line("   Описание: " . ($zone->description ?? 'нет'));
        
        // Проверяем рецепт
        $recipeInstance = $zone->recipeInstance;
        if ($recipeInstance) {
            $recipe = $recipeInstance->recipe;
            $this->info("✅ Рецепт привязан: ID {$recipeInstance->recipe_id} - {$recipe->name}");
            $this->line("   Текущая фаза: " . ($recipeInstance->current_phase_index ?? 0));
        } else {
            $this->warn("⚠️  Рецепт не привязан к зоне 6");
        }
        
        // Проверяем, видна ли зона на фронте
        $this->info('');
        $this->info('🔍 Проверка видимости на фронте...');
        
        // Очищаем кеш для всех пользователей
        $this->info("   Очистка кеша зон...");
        for ($i = 1; $i <= 100; $i++) {
            Cache::forget("zones_list_{$i}");
            Cache::forget("dashboard_data_{$i}");
        }
        // Также очищаем без user_id (если используется такой формат)
        Cache::forget('zones_list');
        Cache::forget('dashboard_data');
        $this->info("   ✅ Кеш очищен");
        
        // Проверяем, есть ли зона в базе при обычном запросе
        $zonesQuery = Zone::query()
            ->select(['id','name','status','description','greenhouse_id'])
            ->get();
        
        $zoneInQuery = $zonesQuery->firstWhere('id', 6);
        if ($zoneInQuery) {
            $this->info("✅ Зона 6 возвращается при обычном запросе из БД");
        } else {
            $this->error("❌ Зона 6 НЕ возвращается при запросе из БД!");
        }
        
        // Список рецептов
        if ($this->option('list-recipes')) {
            $this->info('');
            $this->info('📋 Доступные рецепты:');
            $recipes = Recipe::all(['id', 'name', 'description']);
            if ($recipes->isEmpty()) {
                $this->warn('   Рецептов не найдено');
            } else {
                foreach ($recipes as $recipe) {
                    $phasesCount = $recipe->phases()->count();
                    $this->line("   ID {$recipe->id}: {$recipe->name} ({$phasesCount} фаз)");
                    if ($recipe->description) {
                        $this->line("      Описание: {$recipe->description}");
                    }
                }
            }
        }
        
        // Привязка рецепта
        if ($recipeId = $this->option('attach-recipe')) {
            $this->info('');
            $this->info("🔗 Привязка рецепта ID {$recipeId} к зоне 6...");
            
            $recipe = Recipe::find($recipeId);
            if (!$recipe) {
                $this->error("❌ Рецепт ID {$recipeId} не найден!");
                return 1;
            }
            
            // Проверяем наличие фаз
            $phasesCount = $recipe->phases()->count();
            if ($phasesCount === 0) {
                $this->warn("⚠️  Внимание: рецепт '{$recipe->name}' не имеет фаз!");
                if (!$this->confirm('Привязать рецепт без фаз?')) {
                    $this->info('Отменено');
                    return 0;
                }
            }
            
            try {
                // Используем ZoneService для правильной привязки рецепта
                $newInstance = $zoneService->attachRecipe($zone, $recipeId, now());
                
                $this->info("✅ Рецепт '{$recipe->name}' успешно привязан к зоне 6!");
                $this->line("   Instance ID: {$newInstance->id}");
                $this->line("   Текущая фаза: 0 (первая фаза)");
                
                // Очищаем кеш
                $this->info("   Очистка кеша...");
                for ($i = 1; $i <= 100; $i++) {
                    Cache::forget("zones_list_{$i}");
                    Cache::forget("dashboard_data_{$i}");
                }
                Cache::forget('zones_list');
                Cache::forget('dashboard_data');
                $this->info("   ✅ Кеш очищен");
                
                $this->info("   ✅ Событие ZoneUpdated отправлено через ZoneService");
                
            } catch (\Exception $e) {
                $this->error("❌ Ошибка при привязке рецепта: {$e->getMessage()}");
                $this->line($e->getTraceAsString());
                return 1;
            }
        }
        
        $this->info('');
        $this->info('✅ Проверка завершена');
        
        return 0;
    }
}

