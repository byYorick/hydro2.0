<?php

namespace App\Services;

use App\Enums\GrowCycleStatus;
use App\Models\GrowCycle;
use App\Models\Recipe;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Log;

class RecipeService
{
    /**
     * Создать рецепт
     */
    public function create(array $data, int $plantId): Recipe
    {
        return DB::transaction(function () use ($data, $plantId) {
            $recipeData = $data;
            unset($recipeData['plant_id']);

            $recipe = Recipe::create($recipeData);
            $recipe->plants()->sync([$plantId]);
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
            $recipeData = $data;
            unset($recipeData['plant_id']);
            $recipe->update($recipeData);

            if (array_key_exists('plant_id', $data)) {
                $recipe->plants()->sync([$data['plant_id']]);
            }
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
}
