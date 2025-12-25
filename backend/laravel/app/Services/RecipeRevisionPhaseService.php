<?php

namespace App\Services;

use App\Models\RecipeRevision;
use App\Models\RecipeRevisionPhase;
use Illuminate\Support\Facades\Log;

class RecipeRevisionPhaseService
{
    /**
     * Создать фазу в ревизии
     */
    public function createPhase(RecipeRevision $revision, array $data): RecipeRevisionPhase
    {
        if ($revision->status !== 'DRAFT') {
            throw new \DomainException('Only DRAFT revisions can be edited');
        }

        // Если phase_index не указан, используем следующий доступный
        if (!isset($data['phase_index'])) {
            $maxIndex = $revision->phases()->max('phase_index') ?? -1;
            $data['phase_index'] = $maxIndex + 1;
        }

        return $revision->phases()->create($data);
    }

    /**
     * Обновить фазу
     */
    public function updatePhase(RecipeRevisionPhase $phase, array $data): RecipeRevisionPhase
    {
        $revision = $phase->recipeRevision;

        if ($revision->status !== 'DRAFT') {
            throw new \DomainException('Only DRAFT revisions can be edited');
        }

        $phase->update($data);

        return $phase->fresh()->load('stageTemplate');
    }

    /**
     * Удалить фазу
     */
    public function deletePhase(RecipeRevisionPhase $phase): void
    {
        $revision = $phase->recipeRevision;

        if ($revision->status !== 'DRAFT') {
            throw new \DomainException('Only DRAFT revisions can be edited');
        }

        $phase->delete();

        Log::info('Recipe revision phase deleted', [
            'phase_id' => $phase->id,
            'revision_id' => $revision->id,
        ]);
    }
}

