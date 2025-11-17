<?php

namespace App\Services;

use App\Models\Zone;
use App\Models\ZoneRecipeInstance;
use App\Events\ZoneUpdated;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Log;

class ZoneService
{
    /**
     * Создать зону
     */
    public function create(array $data): Zone
    {
        return DB::transaction(function () use ($data) {
            $zone = Zone::create($data);
            Log::info('Zone created', ['zone_id' => $zone->id, 'name' => $zone->name]);
            
            // Dispatch event для уведомления Python-сервиса
            event(new ZoneUpdated($zone));
            
            return $zone;
        });
    }

    /**
     * Обновить зону
     */
    public function update(Zone $zone, array $data): Zone
    {
        return DB::transaction(function () use ($zone, $data) {
            $zone->update($data);
            Log::info('Zone updated', ['zone_id' => $zone->id]);
            $zone = $zone->fresh();
            
            // Dispatch event для уведомления Python-сервиса
            event(new ZoneUpdated($zone));
            
            return $zone;
        });
    }

    /**
     * Удалить зону (с проверкой инвариантов)
     */
    public function delete(Zone $zone): void
    {
        DB::transaction(function () use ($zone) {
            // Проверка: нельзя удалить зону с активным рецептом
            if ($zone->recipeInstance) {
                throw new \DomainException('Cannot delete zone with active recipe. Please detach recipe first.');
            }

            // Проверка: нельзя удалить зону с привязанными узлами
            if ($zone->nodes()->count() > 0) {
                throw new \DomainException('Cannot delete zone with attached nodes. Please detach nodes first.');
            }

            $zoneId = $zone->id;
            $zoneName = $zone->name;
            $zone->delete();
            Log::info('Zone deleted', ['zone_id' => $zoneId, 'name' => $zoneName]);
        });
    }

    /**
     * Назначить рецепт на зону
     */
    public function attachRecipe(Zone $zone, int $recipeId, ?\DateTimeInterface $startAt = null): ZoneRecipeInstance
    {
        return DB::transaction(function () use ($zone, $recipeId, $startAt) {
            // Удалить предыдущий экземпляр рецепта, если есть
            $existing = $zone->recipeInstance;
            if ($existing) {
                $existing->delete();
            }

            $instance = ZoneRecipeInstance::create([
                'zone_id' => $zone->id,
                'recipe_id' => $recipeId,
                'current_phase_index' => 0,
                'started_at' => $startAt ?? now(),
            ]);

            Log::info('Recipe attached to zone', [
                'zone_id' => $zone->id,
                'recipe_id' => $recipeId,
            ]);

            // Dispatch event для уведомления Python-сервиса
            event(new ZoneUpdated($zone->fresh()));

            // Запустить задачу расчёта аналитики при завершении рецепта (если нужно)
            // Можно запускать периодически или при завершении всех фаз

            return $instance;
        });
    }

    /**
     * Изменить фазу рецепта зоны
     */
    public function changePhase(Zone $zone, int $phaseIndex): ZoneRecipeInstance
    {
        return DB::transaction(function () use ($zone, $phaseIndex) {
            $instance = $zone->recipeInstance;
            if (!$instance) {
                throw new \DomainException('Zone has no active recipe');
            }

            // Проверка: фаза должна существовать в рецепте
            $recipe = $instance->recipe;
            $maxPhaseIndex = $recipe->phases()->max('phase_index') ?? 0;
            if ($phaseIndex < 0 || $phaseIndex > $maxPhaseIndex) {
                throw new \DomainException("Phase index {$phaseIndex} is out of range (0-{$maxPhaseIndex})");
            }

            $instance->update([
                'current_phase_index' => $phaseIndex,
            ]);

            Log::info('Zone phase changed', [
                'zone_id' => $zone->id,
                'phase_index' => $phaseIndex,
            ]);

            // Проверить, завершён ли рецепт (все фазы пройдены)
            $recipe = $instance->recipe;
            $maxPhaseIndex = $recipe->phases()->max('phase_index') ?? 0;
            if ($phaseIndex >= $maxPhaseIndex) {
                // Рецепт завершён - запустить расчёт аналитики
                \App\Jobs\CalculateRecipeAnalyticsJob::dispatch($zone->id, $instance->id);
            }

            // Dispatch event для уведомления Python-сервиса
            event(new ZoneUpdated($zone->fresh()));

            return $instance->fresh();
        });
    }

    /**
     * Пауза/возобновление зоны
     */
    public function pause(Zone $zone): Zone
    {
        if ($zone->status === 'PAUSED') {
            throw new \DomainException('Zone is already paused');
        }

        $zone->update(['status' => 'PAUSED']);
        Log::info('Zone paused', ['zone_id' => $zone->id]);
        $zone = $zone->fresh();
        
        // Dispatch event для уведомления Python-сервиса
        event(new ZoneUpdated($zone));
        
        return $zone;
    }

    /**
     * Возобновление зоны
     */
    public function resume(Zone $zone): Zone
    {
        if ($zone->status !== 'PAUSED') {
            throw new \DomainException('Zone is not paused');
        }

        $zone->update(['status' => 'RUNNING']);
        Log::info('Zone resumed', ['zone_id' => $zone->id]);
        $zone = $zone->fresh();
        
        // Dispatch event для уведомления Python-сервиса
        event(new ZoneUpdated($zone));
        
        return $zone;
    }
}

