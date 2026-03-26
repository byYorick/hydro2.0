<?php

namespace App\Services;

use App\Models\Recipe;
use App\Models\RecipeRevision;
use App\Models\RecipeRevisionPhase;
use App\Models\RecipeRevisionPhaseStep;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Log;

class RecipeRevisionService
{
    /**
     * Создать новую ревизию (пустую или клонированную)
     */
    public function createRevision(
        Recipe $recipe,
        ?int $cloneFromRevisionId = null,
        ?string $description = null,
        int $userId
    ): RecipeRevision {
        return DB::transaction(function () use ($recipe, $cloneFromRevisionId, $description, $userId) {
            $lockedRecipe = Recipe::query()
                ->whereKey($recipe->id)
                ->lockForUpdate()
                ->firstOrFail();

            // Определяем номер новой ревизии под блокировкой рецепта, чтобы
            // параллельные сохранения не получили один и тот же revision_number.
            $lastRevision = RecipeRevision::query()
                ->where('recipe_id', $lockedRecipe->id)
                ->orderByDesc('revision_number')
                ->first();

            $newRevisionNumber = $lastRevision 
                ? $lastRevision->revision_number + 1 
                : 1;

            // Если указана ревизия для клонирования, клонируем её
            if ($cloneFromRevisionId) {
                return $this->cloneRevision($lockedRecipe, $cloneFromRevisionId, $newRevisionNumber, $description, $userId);
            } else {
                // Создаем пустую ревизию
                return RecipeRevision::create([
                    'recipe_id' => $lockedRecipe->id,
                    'revision_number' => $newRevisionNumber,
                    'status' => 'DRAFT',
                    'description' => $description ?? "New revision {$newRevisionNumber}",
                    'created_by' => $userId,
                ]);
            }
        });
    }

    /**
     * Клонировать ревизию
     */
    private function cloneRevision(
        Recipe $recipe,
        int $sourceRevisionId,
        int $newRevisionNumber,
        ?string $description,
        int $userId
    ): RecipeRevision {
        $sourceRevision = RecipeRevision::with('phases.steps')
            ->findOrFail($sourceRevisionId);

        // Создаем новую ревизию
        $newRevision = RecipeRevision::create([
            'recipe_id' => $recipe->id,
            'revision_number' => $newRevisionNumber,
            'status' => 'DRAFT',
            'description' => $description ?? "Cloned from revision {$sourceRevision->revision_number}",
            'created_by' => $userId,
        ]);

        // Клонируем фазы
        foreach ($sourceRevision->phases as $sourcePhase) {
            $phasePayload = $sourcePhase->only($sourcePhase->getFillable());
            unset($phasePayload['recipe_revision_id']);

            $newPhase = $newRevision->phases()->create($phasePayload);

            // Клонируем подшаги
            foreach ($sourcePhase->steps as $sourceStep) {
                $newPhase->steps()->create([
                    'step_index' => $sourceStep->step_index,
                    'name' => $sourceStep->name,
                    'offset_hours' => $sourceStep->offset_hours,
                    'action' => $sourceStep->action,
                    'description' => $sourceStep->description,
                    'targets_override' => $sourceStep->targets_override,
                ]);
            }
        }

        return $newRevision->load(['phases.stageTemplate', 'phases.steps']);
    }

    /**
     * Обновить ревизию
     */
    public function updateRevision(RecipeRevision $revision, array $data): RecipeRevision
    {
        if ($revision->status !== 'DRAFT') {
            throw new \DomainException('Only DRAFT revisions can be edited');
        }

        $revision->update($data);

        return $revision->fresh();
    }

    /**
     * Опубликовать ревизию
     */
    public function publishRevision(RecipeRevision $revision): RecipeRevision
    {
        if ($revision->status !== 'DRAFT') {
            throw new \DomainException('Only DRAFT revisions can be published');
        }

        // Проверяем, что есть хотя бы одна фаза
        if ($revision->phases()->count() === 0) {
            throw new \DomainException('Revision must have at least one phase');
        }

        $revision->update([
            'status' => 'PUBLISHED',
            'published_at' => now(),
        ]);

        Log::info('Recipe revision published', [
            'revision_id' => $revision->id,
            'recipe_id' => $revision->recipe_id,
        ]);

        return $revision->fresh();
    }
}
