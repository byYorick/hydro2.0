<?php

namespace App\Services;

use App\Models\Plant;
use App\Models\Recipe;
use App\Models\RecipeRevision;
use App\Support\Plants\PlantPayloadPreparer;
use App\Support\Recipes\RecipePhasePayloadNormalizer;
use Illuminate\Support\Facades\DB;

class PlantRecipeOrchestrationService
{
    public function __construct(
        private readonly PlantPayloadPreparer $plantPayloadPreparer,
        private readonly RecipeService $recipeService,
        private readonly RecipeRevisionService $recipeRevisionService,
        private readonly RecipeRevisionPhaseService $recipeRevisionPhaseService,
        private readonly RecipePhasePayloadNormalizer $phasePayloadNormalizer,
    ) {}

    /**
     * @param  array<string, mixed>  $plantData
     * @param  array<string, mixed>  $recipeData
     * @param  array<int, array<string, mixed>>  $phases
     * @return array{plant: Plant, recipe: Recipe, revision: RecipeRevision}
     */
    public function createPlantWithRecipe(array $plantData, array $recipeData, array $phases, int $userId): array
    {
        return DB::transaction(function () use ($plantData, $recipeData, $phases, $userId): array {
            $plant = Plant::create($this->plantPayloadPreparer->prepare($plantData));

            $recipe = $this->recipeService->create([
                'name' => (string) ($recipeData['name'] ?? ''),
                'description' => $recipeData['description'] ?? null,
            ], $plant->id);

            $revision = $this->recipeRevisionService->createRevision(
                $recipe,
                null,
                isset($recipeData['revision_description']) && is_string($recipeData['revision_description'])
                    ? $recipeData['revision_description']
                    : 'Initial revision from plant recipe flow',
                $userId
            );

            foreach ($phases as $phaseData) {
                $normalized = $this->phasePayloadNormalizer->normalizeForWrite($phaseData);
                $this->recipeRevisionPhaseService->createPhase($revision, $normalized);
            }

            $publishedRevision = $this->recipeRevisionService->publishRevision($revision);

            return [
                'plant' => $plant->fresh(),
                'recipe' => $recipe->fresh(),
                'revision' => $publishedRevision->fresh(),
            ];
        });
    }
}
