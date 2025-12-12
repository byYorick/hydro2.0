<?php

namespace App\Services;

use App\Events\GrowCycleUpdated;
use App\Models\GrowCycle;
use App\Models\GrowStageTemplate;
use App\Models\Recipe;
use App\Models\RecipeStageMap;
use App\Models\Zone;
use App\Models\ZoneRecipeInstance;
use App\Enums\GrowCycleStatus;
use Carbon\Carbon;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Log;

class GrowCycleService
{
    /**
     * Создать новый цикл выращивания
     */
    public function createCycle(
        Zone $zone,
        ?Recipe $recipe = null,
        ?int $plantId = null,
        array $settings = []
    ): GrowCycle {
        $recipe = $recipe ?? $zone->recipeInstance?->recipe;
        
        if (!$recipe) {
            throw new \DomainException('Recipe is required to create a grow cycle');
        }

        return DB::transaction(function () use ($zone, $recipe, $plantId, $settings) {
            $cycle = GrowCycle::create([
                'greenhouse_id' => $zone->greenhouse_id,
                'zone_id' => $zone->id,
                'plant_id' => $plantId,
                'recipe_id' => $recipe->id,
                'zone_recipe_instance_id' => $zone->recipeInstance?->id,
                'status' => GrowCycleStatus::PLANNED,
                'settings' => $settings,
            ]);

            // Генерируем stage-map для рецепта, если его еще нет
            $this->ensureRecipeStageMap($recipe);

            Log::info('Grow cycle created', [
                'cycle_id' => $cycle->id,
                'zone_id' => $zone->id,
                'recipe_id' => $recipe->id,
            ]);

            return $cycle;
        });
    }

    /**
     * Запустить цикл (посадка)
     */
    public function startCycle(GrowCycle $cycle, ?Carbon $plantingAt = null): GrowCycle
    {
        if ($cycle->status !== GrowCycleStatus::PLANNED) {
            throw new \DomainException('Cycle must be in PLANNED status to start');
        }

        return DB::transaction(function () use ($cycle, $plantingAt) {
            $plantingAt = $plantingAt ?? now();
            
            $cycle->update([
                'status' => GrowCycleStatus::RUNNING,
                'planting_at' => $plantingAt,
                'started_at' => $plantingAt,
                'recipe_started_at' => $plantingAt,
            ]);

            // Вычисляем первую стадию и устанавливаем её
            $this->computeStageFromRecipeInstance($cycle);
            
            // Вычисляем ожидаемую дату сбора
            $this->computeExpectedHarvest($cycle);

            Log::info('Grow cycle started', [
                'cycle_id' => $cycle->id,
                'planting_at' => $plantingAt,
            ]);

            return $cycle->fresh();
        });
    }

    /**
     * Переход на следующую стадию (автоматически или вручную)
     */
    public function advanceStage(GrowCycle $cycle, ?string $targetStageCode = null): GrowCycle
    {
        if ($cycle->status !== GrowCycleStatus::RUNNING) {
            throw new \DomainException('Cycle must be RUNNING to advance stage');
        }

        return DB::transaction(function () use ($cycle, $targetStageCode) {
            $recipe = $cycle->recipe;
            if (!$recipe) {
                throw new \DomainException('Cycle must have a recipe to advance stage');
            }

            $stageMaps = $recipe->stageMaps()->orderBy('order_index')->get();
            
            if ($targetStageCode) {
                // Ручной переход на указанную стадию
                $targetMap = $stageMaps->firstWhere('stageTemplate.code', $targetStageCode);
                if (!$targetMap) {
                    throw new \DomainException("Stage {$targetStageCode} not found in recipe stage map");
                }
            } else {
                // Автоматический переход на следующую стадию
                $currentMap = $stageMaps->firstWhere('stageTemplate.code', $cycle->current_stage_code);
                if (!$currentMap) {
                    // Если текущей стадии нет в маппинге, берем первую
                    $targetMap = $stageMaps->first();
                } else {
                    $currentIndex = $currentMap->order_index;
                    $targetMap = $stageMaps->firstWhere('order_index', $currentIndex + 1);
                }

                if (!$targetMap) {
                    throw new \DomainException('No next stage available');
                }
            }

            $stageTemplate = $targetMap->stageTemplate;
            
            $oldStageCode = $cycle->current_stage_code;
            
            $cycle->update([
                'current_stage_code' => $stageTemplate->code,
                'current_stage_started_at' => now(),
            ]);
            
            $cycle->refresh();

            // Отправляем событие об обновлении цикла для автоматического обновления targets в AE
            GrowCycleUpdated::dispatch($cycle, 'STAGE_ADVANCED');

            Log::info('Grow cycle stage advanced', [
                'cycle_id' => $cycle->id,
                'old_stage_code' => $oldStageCode,
                'new_stage_code' => $stageTemplate->code,
            ]);

            return $cycle->fresh();
        });
    }

    /**
     * Вычислить текущую стадию на основе recipe instance
     */
    public function computeStageFromRecipeInstance(GrowCycle $cycle): void
    {
        $recipe = $cycle->recipe;
        $zone = $cycle->zone;
        
        if (!$recipe || !$zone->recipeInstance) {
            return;
        }

        $stageMaps = $recipe->stageMaps()->with('stageTemplate')->orderBy('order_index')->get();
        
        if ($stageMaps->isEmpty()) {
            // Если нет stage-map, создаем его автоматически
            $this->ensureRecipeStageMap($recipe);
            $stageMaps = $recipe->stageMaps()->with('stageTemplate')->orderBy('order_index')->get();
        }

        $plantingAt = $cycle->planting_at ?? $cycle->started_at;
        if (!$plantingAt) {
            return;
        }

        $daysSincePlanting = now()->diffInDays($plantingAt);
        
        // Находим текущую стадию на основе offset_days
        $currentMap = null;
        foreach ($stageMaps as $map) {
            $startOffset = $map->start_offset_days ?? 0;
            $endOffset = $map->end_offset_days;
            
            if ($daysSincePlanting >= $startOffset) {
                if ($endOffset === null || $daysSincePlanting < $endOffset) {
                    $currentMap = $map;
                    break;
                }
            }
        }

        // Если не нашли по offset, берем первую стадию
        if (!$currentMap) {
            $currentMap = $stageMaps->first();
        }

        if ($currentMap) {
            $oldStageCode = $cycle->current_stage_code;
            $newStageCode = $currentMap->stageTemplate->code;
            
            $cycle->update([
                'current_stage_code' => $newStageCode,
                'current_stage_started_at' => $cycle->current_stage_started_at ?? now(),
            ]);
            
            // Если стадия изменилась, отправляем событие для обновления targets
            if ($oldStageCode !== $newStageCode) {
                $cycle->refresh();
                GrowCycleUpdated::dispatch($cycle, 'STAGE_COMPUTED');
            }
        }
    }

    /**
     * Вычислить ожидаемую дату сбора урожая
     */
    public function computeExpectedHarvest(GrowCycle $cycle): void
    {
        $recipe = $cycle->recipe;
        if (!$recipe) {
            return;
        }

        $stageMaps = $recipe->stageMaps()->with('stageTemplate')->orderBy('order_index')->get();
        
        if ($stageMaps->isEmpty()) {
            return;
        }

        $plantingAt = $cycle->planting_at ?? $cycle->started_at;
        if (!$plantingAt) {
            return;
        }

        // Находим последнюю стадию (обычно HARVEST)
        $lastMap = $stageMaps->last();
        $harvestOffset = $lastMap->end_offset_days ?? $lastMap->start_offset_days;

        if ($harvestOffset) {
            $expectedHarvestAt = Carbon::parse($plantingAt)->addDays($harvestOffset);
            $cycle->update(['expected_harvest_at' => $expectedHarvestAt]);
        } else {
            // Если offset не задан, вычисляем на основе default_duration_days стадий
            $totalDays = 0;
            foreach ($stageMaps as $map) {
                $duration = $map->end_offset_days 
                    ? ($map->end_offset_days - ($map->start_offset_days ?? 0))
                    : ($map->stageTemplate->default_duration_days ?? 0);
                $totalDays += $duration;
            }
            
            if ($totalDays > 0) {
                $expectedHarvestAt = Carbon::parse($plantingAt)->addDays($totalDays);
                $cycle->update(['expected_harvest_at' => $expectedHarvestAt]);
            }
        }
    }

    /**
     * Убедиться, что у рецепта есть stage-map (создать автоматически, если нет)
     */
    public function ensureRecipeStageMap(Recipe $recipe): void
    {
        if ($recipe->stageMaps()->exists()) {
            return;
        }

        // Автоматически генерируем stage-map на основе фаз рецепта
        $phases = $recipe->phases()->orderBy('phase_index')->get();
        
        if ($phases->isEmpty()) {
            return;
        }

        // Получаем стандартные шаблоны стадий
        $templates = GrowStageTemplate::orderBy('order_index')->get();
        
        if ($templates->isEmpty()) {
            // Если шаблонов нет, создаем базовые
            $this->createDefaultStageTemplates();
            $templates = GrowStageTemplate::orderBy('order_index')->get();
        }

        // Маппим фазы на стадии
        $phaseCount = $phases->count();
        $stageCount = $templates->count();
        
        $phasesPerStage = max(1, (int) ceil($phaseCount / $stageCount));
        
        $orderIndex = 0;
        $phaseIndex = 0;
        
        foreach ($templates as $template) {
            $phaseIndices = [];
            for ($i = 0; $i < $phasesPerStage && $phaseIndex < $phaseCount; $i++) {
                $phaseIndices[] = $phases[$phaseIndex]->phase_index;
                $phaseIndex++;
            }

            if (!empty($phaseIndices) || $orderIndex === 0) {
                // Первая стадия всегда создается, даже если фаз нет
                RecipeStageMap::create([
                    'recipe_id' => $recipe->id,
                    'stage_template_id' => $template->id,
                    'order_index' => $orderIndex,
                    'phase_indices' => $phaseIndices,
                    'start_offset_days' => $orderIndex === 0 ? 0 : null, // Первая стадия начинается с 0
                ]);
                $orderIndex++;
            }
        }
    }

    /**
     * Создать стандартные шаблоны стадий
     */
    private function createDefaultStageTemplates(): void
    {
        $defaultStages = [
            ['name' => 'Посадка', 'code' => 'PLANTING', 'order' => 0, 'duration' => 1, 'color' => '#10b981', 'icon' => '🌱'],
            ['name' => 'Укоренение', 'code' => 'ROOTING', 'order' => 1, 'duration' => 7, 'color' => '#3b82f6', 'icon' => '🌿'],
            ['name' => 'Вега', 'code' => 'VEG', 'order' => 2, 'duration' => 21, 'color' => '#22c55e', 'icon' => '🌳'],
            ['name' => 'Цветение', 'code' => 'FLOWER', 'order' => 3, 'duration' => 14, 'color' => '#f59e0b', 'icon' => '🌸'],
            ['name' => 'Плодоношение', 'code' => 'FRUIT', 'order' => 4, 'duration' => 21, 'color' => '#ef4444', 'icon' => '🍅'],
            ['name' => 'Сбор', 'code' => 'HARVEST', 'order' => 5, 'duration' => 1, 'color' => '#8b5cf6', 'icon' => '✂️'],
        ];

        foreach ($defaultStages as $stage) {
            GrowStageTemplate::create([
                'name' => $stage['name'],
                'code' => $stage['code'],
                'order_index' => $stage['order'],
                'default_duration_days' => $stage['duration'],
                'ui_meta' => [
                    'color' => $stage['color'],
                    'icon' => $stage['icon'],
                    'description' => $stage['name'],
                ],
            ]);
        }
    }
}

