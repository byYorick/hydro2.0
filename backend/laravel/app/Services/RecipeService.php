<?php

namespace App\Services;

use App\Models\Recipe;
use App\Models\RecipePhase;
use App\Models\Zone;
use App\Models\GrowCycle;
use App\Enums\GrowCycleStatus;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Log;

class RecipeService
{
    /**
     * Создать рецепт
     */
    public function create(array $data): Recipe
    {
        return DB::transaction(function () use ($data) {
            $recipe = Recipe::create($data);
            Log::info('Recipe created', ['recipe_id' => $recipe->id, 'name' => $recipe->name]);
            return $recipe;
        });
    }

    /**
     * Обновить рецепт
     */
    public function update(Recipe $recipe, array $data): Recipe
    {
        return DB::transaction(function () use ($recipe, $data) {
            $recipe->update($data);
            Log::info('Recipe updated', ['recipe_id' => $recipe->id]);
            return $recipe->fresh();
        });
    }

    /**
     * Удалить рецепт (с проверкой инвариантов)
     */
    public function delete(Recipe $recipe): void
    {
        DB::transaction(function () use ($recipe) {
            // Проверка: нельзя удалить рецепт, который используется в активных циклах
            $activeCycles = GrowCycle::whereHas('recipeRevision', function ($query) use ($recipe) {
                $query->where('recipe_id', $recipe->id);
            })->whereIn('status', [GrowCycleStatus::PLANNED, GrowCycleStatus::RUNNING, GrowCycleStatus::PAUSED])->count();
            
            if ($activeCycles > 0) {
                throw new \DomainException("Cannot delete recipe that is used in {$activeCycles} active grow cycle(s). Please finish or abort cycles first.");
            }

            $recipeId = $recipe->id;
            $recipeName = $recipe->name;
            $recipe->delete();
            Log::info('Recipe deleted', ['recipe_id' => $recipeId, 'name' => $recipeName]);
        });
    }

    /**
     * Добавить фазу к рецепту
     */
    public function addPhase(Recipe $recipe, array $phaseData): RecipePhase
    {
        return DB::transaction(function () use ($recipe, $phaseData) {
            // Проверка: фазы не должны пересекаться по времени
            // (это можно расширить в будущем, если нужно проверять пересечения)

            $phase = RecipePhase::create(array_merge($phaseData, [
                'recipe_id' => $recipe->id,
            ]));

            Log::info('Phase added to recipe', [
                'recipe_id' => $recipe->id,
                'phase_id' => $phase->id,
            ]);

            return $phase;
        });
    }

    /**
     * Обновить фазу рецепта
     */
    public function updatePhase(RecipePhase $phase, array $data): RecipePhase
    {
        return DB::transaction(function () use ($phase, $data) {
            $phase->update($data);
            Log::info('Phase updated', ['phase_id' => $phase->id]);
            return $phase->fresh();
        });
    }

    /**
     * Удалить фазу рецепта
     */
    public function deletePhase(RecipePhase $phase): void
    {
        DB::transaction(function () use ($phase) {
            $phaseId = $phase->id;
            $recipeId = $phase->recipe_id;
            $phase->delete();
            Log::info('Phase deleted', ['phase_id' => $phaseId, 'recipe_id' => $recipeId]);
        });
    }

    /**
     * Применить рецепт к зоне
     * 
     * @deprecated Используйте GrowCycleService::createCycle() с RecipeRevision вместо этого метода
     */
    public function applyToZone(Recipe $recipe, Zone $zone, ?\DateTimeInterface $startAt = null)
    {
        Log::warning('RecipeService::applyToZone() is deprecated. Use GrowCycleService::createCycle() with a RecipeRevision instead.', [
            'recipe_id' => $recipe->id,
            'zone_id' => $zone->id,
        ]);

        throw new \DomainException('RecipeService::applyToZone() is deprecated. Please use GrowCycleService::createCycle() with a RecipeRevision to create a new grow cycle.');
    }
}

