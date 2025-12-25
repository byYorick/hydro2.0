<?php

namespace App\Http\Controllers;

use App\Models\Recipe;
use App\Models\RecipeRevision;
use App\Helpers\ZoneAccessHelper;
use Illuminate\Http\JsonResponse;
use Illuminate\Http\Request;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Log;
use Symfony\Component\HttpFoundation\Response;

class RecipeRevisionController extends Controller
{
    /**
     * Получить ревизию рецепта с фазами
     * GET /api/recipe-revisions/{recipeRevision}
     */
    public function show(RecipeRevision $recipeRevision): JsonResponse
    {
        $recipeRevision->load([
            'phases.stageTemplate',
            'phases.steps',
            'recipe',
            'creator',
        ]);

        return response()->json([
            'status' => 'ok',
            'data' => $recipeRevision,
        ]);
    }

    /**
     * Создать новую ревизию на основе существующей (clone)
     * POST /api/recipes/{recipe}/revisions
     */
    public function store(Request $request, Recipe $recipe): JsonResponse
    {
        $user = $request->user();
        if (!$user) {
            return response()->json([
                'status' => 'error',
                'message' => 'Unauthorized',
            ], 401);
        }

        // TODO: Проверка прав (только agronomist может создавать ревизии)
        // if (!$user->hasRole('agronomist')) { ... }

        $data = $request->validate([
            'clone_from_revision_id' => ['nullable', 'integer', 'exists:recipe_revisions,id'],
            'description' => ['nullable', 'string'],
        ]);

        try {
            return DB::transaction(function () use ($recipe, $data, $user) {
                // Определяем номер новой ревизии
                $lastRevision = $recipe->revisions()
                    ->orderBy('revision_number', 'desc')
                    ->first();
                
                $newRevisionNumber = $lastRevision 
                    ? $lastRevision->revision_number + 1 
                    : 1;

                // Если указана ревизия для клонирования, клонируем её
                if (isset($data['clone_from_revision_id'])) {
                    $sourceRevision = RecipeRevision::with('phases.steps')
                        ->findOrFail($data['clone_from_revision_id']);

                    // Создаем новую ревизию
                    $newRevision = RecipeRevision::create([
                        'recipe_id' => $recipe->id,
                        'revision_number' => $newRevisionNumber,
                        'status' => 'DRAFT',
                        'description' => $data['description'] ?? "Cloned from revision {$sourceRevision->revision_number}",
                        'created_by' => $user->id,
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

                    $newRevision->load(['phases.stageTemplate', 'phases.steps']);

                    return response()->json([
                        'status' => 'ok',
                        'data' => $newRevision,
                    ], Response::HTTP_CREATED);
                } else {
                    // Создаем пустую ревизию
                    $newRevision = RecipeRevision::create([
                        'recipe_id' => $recipe->id,
                        'revision_number' => $newRevisionNumber,
                        'status' => 'DRAFT',
                        'description' => $data['description'] ?? "New revision {$newRevisionNumber}",
                        'created_by' => $user->id,
                    ]);

                    return response()->json([
                        'status' => 'ok',
                        'data' => $newRevision,
                    ], Response::HTTP_CREATED);
                }
            });
        } catch (\Exception $e) {
            Log::error('Failed to create recipe revision', [
                'recipe_id' => $recipe->id,
                'error' => $e->getMessage(),
            ]);

            return response()->json([
                'status' => 'error',
                'message' => $e->getMessage(),
            ], Response::HTTP_INTERNAL_SERVER_ERROR);
        }
    }

    /**
     * Редактировать черновик ревизии
     * PATCH /api/recipe-revisions/{recipeRevision}
     */
    public function update(Request $request, RecipeRevision $recipeRevision): JsonResponse
    {
        $user = $request->user();
        if (!$user) {
            return response()->json([
                'status' => 'error',
                'message' => 'Unauthorized',
            ], 401);
        }

        // Только черновики можно редактировать
        if ($recipeRevision->status !== 'DRAFT') {
            return response()->json([
                'status' => 'error',
                'message' => 'Only DRAFT revisions can be edited',
            ], Response::HTTP_UNPROCESSABLE_ENTITY);
        }

        $data = $request->validate([
            'description' => ['nullable', 'string'],
        ]);

        try {
            $recipeRevision->update($data);

            return response()->json([
                'status' => 'ok',
                'data' => $recipeRevision->fresh(),
            ]);
        } catch (\Exception $e) {
            Log::error('Failed to update recipe revision', [
                'revision_id' => $recipeRevision->id,
                'error' => $e->getMessage(),
            ]);

            return response()->json([
                'status' => 'error',
                'message' => $e->getMessage(),
            ], Response::HTTP_INTERNAL_SERVER_ERROR);
        }
    }

    /**
     * Опубликовать ревизию (lock)
     * POST /api/recipe-revisions/{recipeRevision}/publish
     */
    public function publish(Request $request, RecipeRevision $recipeRevision): JsonResponse
    {
        $user = $request->user();
        if (!$user) {
            return response()->json([
                'status' => 'error',
                'message' => 'Unauthorized',
            ], 401);
        }

        // TODO: Проверка прав (только agronomist может публиковать)
        // if (!$user->hasRole('agronomist')) { ... }

        // Только черновики можно публиковать
        if ($recipeRevision->status !== 'DRAFT') {
            return response()->json([
                'status' => 'error',
                'message' => 'Only DRAFT revisions can be published',
            ], Response::HTTP_UNPROCESSABLE_ENTITY);
        }

        // Проверяем, что есть хотя бы одна фаза
        if ($recipeRevision->phases()->count() === 0) {
            return response()->json([
                'status' => 'error',
                'message' => 'Revision must have at least one phase',
            ], Response::HTTP_UNPROCESSABLE_ENTITY);
        }

        try {
            $recipeRevision->update([
                'status' => 'PUBLISHED',
                'published_at' => now(),
            ]);

            Log::info('Recipe revision published', [
                'revision_id' => $recipeRevision->id,
                'recipe_id' => $recipeRevision->recipe_id,
                'user_id' => $user->id,
            ]);

            return response()->json([
                'status' => 'ok',
                'data' => $recipeRevision->fresh(),
            ]);
        } catch (\Exception $e) {
            Log::error('Failed to publish recipe revision', [
                'revision_id' => $recipeRevision->id,
                'error' => $e->getMessage(),
            ]);

            return response()->json([
                'status' => 'error',
                'message' => $e->getMessage(),
            ], Response::HTTP_INTERNAL_SERVER_ERROR);
        }
    }
}

