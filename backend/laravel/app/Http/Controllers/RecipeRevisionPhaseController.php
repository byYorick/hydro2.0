<?php

namespace App\Http\Controllers;

use App\Models\RecipeRevision;
use App\Models\RecipeRevisionPhase;
use App\Services\RecipeRevisionPhaseService;
use Illuminate\Http\JsonResponse;
use Illuminate\Http\Request;
use Illuminate\Support\Facades\Log;
use Symfony\Component\HttpFoundation\Response;

class RecipeRevisionPhaseController extends Controller
{
    public function __construct(
        private RecipeRevisionPhaseService $phaseService
    ) {
    }

    /**
     * Создать фазу в ревизии рецепта
     * POST /api/recipe-revisions/{recipeRevision}/phases
     */
    public function store(Request $request, RecipeRevision $recipeRevision): JsonResponse
    {
        $user = $request->user();
        if (!$user) {
            return response()->json([
                'status' => 'error',
                'message' => 'Unauthorized',
            ], 401);
        }

        $data = $request->validate([
            'stage_template_id' => ['nullable', 'integer', 'exists:grow_stage_templates,id'],
            'phase_index' => ['nullable', 'integer', 'min:0'],
            'name' => ['required', 'string', 'max:255'],
            // Обязательные параметры (MVP)
            'ph_target' => ['nullable', 'numeric', 'min:0', 'max:14'],
            'ph_min' => ['nullable', 'numeric', 'min:0', 'max:14'],
            'ph_max' => ['nullable', 'numeric', 'min:0', 'max:14'],
            'ec_target' => ['nullable', 'numeric', 'min:0'],
            'ec_min' => ['nullable', 'numeric', 'min:0'],
            'ec_max' => ['nullable', 'numeric', 'min:0'],
            'irrigation_mode' => ['nullable', 'string', 'in:SUBSTRATE,RECIRC'],
            'irrigation_interval_sec' => ['nullable', 'integer', 'min:0'],
            'irrigation_duration_sec' => ['nullable', 'integer', 'min:0'],
            // Опциональные параметры
            'lighting_photoperiod_hours' => ['nullable', 'integer', 'min:0', 'max:24'],
            'lighting_start_time' => ['nullable', 'date_format:H:i:s'],
            'mist_interval_sec' => ['nullable', 'integer', 'min:0'],
            'mist_duration_sec' => ['nullable', 'integer', 'min:0'],
            'mist_mode' => ['nullable', 'string', 'in:NORMAL,SPRAY'],
            'temp_air_target' => ['nullable', 'numeric'],
            'humidity_target' => ['nullable', 'numeric', 'min:0', 'max:100'],
            'co2_target' => ['nullable', 'integer', 'min:0'],
            'progress_model' => ['nullable', 'string', 'in:TIME,TIME_WITH_TEMP_CORRECTION,GDD,DLI'],
            'duration_hours' => ['nullable', 'integer', 'min:0'],
            'duration_days' => ['nullable', 'integer', 'min:0'],
            'base_temp_c' => ['nullable', 'numeric'],
            'target_gdd' => ['nullable', 'numeric', 'min:0'],
            'dli_target' => ['nullable', 'numeric', 'min:0'],
            'extensions' => ['nullable', 'array'],
        ]);

        try {
            $phase = $this->phaseService->createPhase($recipeRevision, $data);

            return response()->json([
                'status' => 'ok',
                'data' => $phase->load('stageTemplate'),
            ], Response::HTTP_CREATED);
        } catch (\DomainException $e) {
            return response()->json([
                'status' => 'error',
                'message' => $e->getMessage(),
            ], Response::HTTP_UNPROCESSABLE_ENTITY);
        } catch (\Exception $e) {
            Log::error('Failed to create recipe revision phase', [
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
     * Обновить фазу ревизии
     * PATCH /api/recipe-revision-phases/{recipeRevisionPhase}
     */
    public function update(Request $request, RecipeRevisionPhase $recipeRevisionPhase): JsonResponse
    {
        $user = $request->user();
        if (!$user) {
            return response()->json([
                'status' => 'error',
                'message' => 'Unauthorized',
            ], 401);
        }

        $data = $request->validate([
            'stage_template_id' => ['nullable', 'integer', 'exists:grow_stage_templates,id'],
            'phase_index' => ['nullable', 'integer', 'min:0'],
            'name' => ['sometimes', 'required', 'string', 'max:255'],
            // Все параметры опциональны при обновлении
            'ph_target' => ['nullable', 'numeric', 'min:0', 'max:14'],
            'ph_min' => ['nullable', 'numeric', 'min:0', 'max:14'],
            'ph_max' => ['nullable', 'numeric', 'min:0', 'max:14'],
            'ec_target' => ['nullable', 'numeric', 'min:0'],
            'ec_min' => ['nullable', 'numeric', 'min:0'],
            'ec_max' => ['nullable', 'numeric', 'min:0'],
            'irrigation_mode' => ['nullable', 'string', 'in:SUBSTRATE,RECIRC'],
            'irrigation_interval_sec' => ['nullable', 'integer', 'min:0'],
            'irrigation_duration_sec' => ['nullable', 'integer', 'min:0'],
            'lighting_photoperiod_hours' => ['nullable', 'integer', 'min:0', 'max:24'],
            'lighting_start_time' => ['nullable', 'date_format:H:i:s'],
            'mist_interval_sec' => ['nullable', 'integer', 'min:0'],
            'mist_duration_sec' => ['nullable', 'integer', 'min:0'],
            'mist_mode' => ['nullable', 'string', 'in:NORMAL,SPRAY'],
            'temp_air_target' => ['nullable', 'numeric'],
            'humidity_target' => ['nullable', 'numeric', 'min:0', 'max:100'],
            'co2_target' => ['nullable', 'integer', 'min:0'],
            'progress_model' => ['nullable', 'string', 'in:TIME,TIME_WITH_TEMP_CORRECTION,GDD,DLI'],
            'duration_hours' => ['nullable', 'integer', 'min:0'],
            'duration_days' => ['nullable', 'integer', 'min:0'],
            'base_temp_c' => ['nullable', 'numeric'],
            'target_gdd' => ['nullable', 'numeric', 'min:0'],
            'dli_target' => ['nullable', 'numeric', 'min:0'],
            'extensions' => ['nullable', 'array'],
        ]);

        try {
            $phase = $this->phaseService->updatePhase($recipeRevisionPhase, $data);

            return response()->json([
                'status' => 'ok',
                'data' => $phase,
            ]);
        } catch (\DomainException $e) {
            return response()->json([
                'status' => 'error',
                'message' => $e->getMessage(),
            ], Response::HTTP_UNPROCESSABLE_ENTITY);
        } catch (\Exception $e) {
            Log::error('Failed to update recipe revision phase', [
                'phase_id' => $recipeRevisionPhase->id,
                'error' => $e->getMessage(),
            ]);

            return response()->json([
                'status' => 'error',
                'message' => $e->getMessage(),
            ], Response::HTTP_INTERNAL_SERVER_ERROR);
        }
    }

    /**
     * Удалить фазу ревизии
     * DELETE /api/recipe-revision-phases/{recipeRevisionPhase}
     */
    public function destroy(RecipeRevisionPhase $recipeRevisionPhase): JsonResponse
    {
        $user = request()->user();
        if (!$user) {
            return response()->json([
                'status' => 'error',
                'message' => 'Unauthorized',
            ], 401);
        }

        try {
            $this->phaseService->deletePhase($recipeRevisionPhase);

            return response()->json([
                'status' => 'ok',
                'message' => 'Phase deleted',
            ]);
        } catch (\DomainException $e) {
            return response()->json([
                'status' => 'error',
                'message' => $e->getMessage(),
            ], Response::HTTP_UNPROCESSABLE_ENTITY);
        } catch (\Exception $e) {
            Log::error('Failed to delete recipe revision phase', [
                'phase_id' => $recipeRevisionPhase->id,
                'error' => $e->getMessage(),
            ]);

            return response()->json([
                'status' => 'error',
                'message' => $e->getMessage(),
            ], Response::HTTP_INTERNAL_SERVER_ERROR);
        }
    }
}

