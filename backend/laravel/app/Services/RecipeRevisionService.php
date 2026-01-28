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
            // Определяем номер новой ревизии
            $lastRevision = $recipe->revisions()
                ->orderBy('revision_number', 'desc')
                ->first();
            
            $newRevisionNumber = $lastRevision 
                ? $lastRevision->revision_number + 1 
                : 1;

            // Если указана ревизия для клонирования, клонируем её
            if ($cloneFromRevisionId) {
                return $this->cloneRevision($recipe, $cloneFromRevisionId, $newRevisionNumber, $description, $userId);
            } else {
                // Создаем пустую ревизию
                return RecipeRevision::create([
                    'recipe_id' => $recipe->id,
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
            $newPhase = $newRevision->phases()->create([
                'stage_template_id' => $sourcePhase->stage_template_id,
                'phase_index' => $sourcePhase->phase_index,
                'name' => $sourcePhase->name,
                // Копируем все параметры
                'ph_target' => $sourcePhase->ph_target,
                'ph_min' => $sourcePhase->ph_min,
                'ph_max' => $sourcePhase->ph_max,
                'ec_target' => $sourcePhase->ec_target,
                'ec_min' => $sourcePhase->ec_min,
                'ec_max' => $sourcePhase->ec_max,
                'irrigation_mode' => $sourcePhase->irrigation_mode,
                'irrigation_interval_sec' => $sourcePhase->irrigation_interval_sec,
                'irrigation_duration_sec' => $sourcePhase->irrigation_duration_sec,
                'lighting_photoperiod_hours' => $sourcePhase->lighting_photoperiod_hours,
                'lighting_start_time' => $sourcePhase->lighting_start_time,
                'mist_interval_sec' => $sourcePhase->mist_interval_sec,
                'mist_duration_sec' => $sourcePhase->mist_duration_sec,
                'mist_mode' => $sourcePhase->mist_mode,
                'temp_air_target' => $sourcePhase->temp_air_target,
                'humidity_target' => $sourcePhase->humidity_target,
                'co2_target' => $sourcePhase->co2_target,
                'progress_model' => $sourcePhase->progress_model,
                'duration_hours' => $sourcePhase->duration_hours,
                'duration_days' => $sourcePhase->duration_days,
                'base_temp_c' => $sourcePhase->base_temp_c,
                'target_gdd' => $sourcePhase->target_gdd,
                'dli_target' => $sourcePhase->dli_target,
                'extensions' => $sourcePhase->extensions,
            ]);

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

