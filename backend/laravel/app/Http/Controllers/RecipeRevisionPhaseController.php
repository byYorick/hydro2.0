<?php

namespace App\Http\Controllers;

use App\Models\RecipeRevision;
use App\Models\RecipeRevisionPhase;
use App\Services\RecipeRevisionPhaseService;
use Illuminate\Http\JsonResponse;
use Illuminate\Http\Request;
use Illuminate\Support\Facades\Log;
use Illuminate\Support\Facades\Validator;
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
            'nutrient_program_code' => ['nullable', 'string', 'max:64'],
            'nutrient_mode' => ['nullable', 'string', 'in:ratio_ec_pid,delta_ec_by_k,dose_ml_l_only'],
            'nutrient_npk_ratio_pct' => ['nullable', 'numeric', 'min:0', 'max:100'],
            'nutrient_calcium_ratio_pct' => ['nullable', 'numeric', 'min:0', 'max:100'],
            'nutrient_magnesium_ratio_pct' => ['nullable', 'numeric', 'min:0', 'max:100'],
            'nutrient_micro_ratio_pct' => ['nullable', 'numeric', 'min:0', 'max:100'],
            'nutrient_npk_dose_ml_l' => ['nullable', 'numeric', 'min:0'],
            'nutrient_calcium_dose_ml_l' => ['nullable', 'numeric', 'min:0'],
            'nutrient_magnesium_dose_ml_l' => ['nullable', 'numeric', 'min:0'],
            'nutrient_micro_dose_ml_l' => ['nullable', 'numeric', 'min:0'],
            'nutrient_npk_product_id' => ['nullable', 'integer', 'exists:nutrient_products,id'],
            'nutrient_calcium_product_id' => ['nullable', 'integer', 'exists:nutrient_products,id'],
            'nutrient_magnesium_product_id' => ['nullable', 'integer', 'exists:nutrient_products,id'],
            'nutrient_micro_product_id' => ['nullable', 'integer', 'exists:nutrient_products,id'],
            'nutrient_dose_delay_sec' => ['nullable', 'integer', 'min:0', 'max:3600'],
            'nutrient_ec_stop_tolerance' => ['nullable', 'numeric', 'min:0', 'max:5'],
            'nutrient_solution_volume_l' => ['nullable', 'numeric', 'min:0.1', 'max:100000'],
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
        $this->validateNutritionRatioSum($data);

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
            'nutrient_program_code' => ['nullable', 'string', 'max:64'],
            'nutrient_mode' => ['nullable', 'string', 'in:ratio_ec_pid,delta_ec_by_k,dose_ml_l_only'],
            'nutrient_npk_ratio_pct' => ['nullable', 'numeric', 'min:0', 'max:100'],
            'nutrient_calcium_ratio_pct' => ['nullable', 'numeric', 'min:0', 'max:100'],
            'nutrient_magnesium_ratio_pct' => ['nullable', 'numeric', 'min:0', 'max:100'],
            'nutrient_micro_ratio_pct' => ['nullable', 'numeric', 'min:0', 'max:100'],
            'nutrient_npk_dose_ml_l' => ['nullable', 'numeric', 'min:0'],
            'nutrient_calcium_dose_ml_l' => ['nullable', 'numeric', 'min:0'],
            'nutrient_magnesium_dose_ml_l' => ['nullable', 'numeric', 'min:0'],
            'nutrient_micro_dose_ml_l' => ['nullable', 'numeric', 'min:0'],
            'nutrient_npk_product_id' => ['nullable', 'integer', 'exists:nutrient_products,id'],
            'nutrient_calcium_product_id' => ['nullable', 'integer', 'exists:nutrient_products,id'],
            'nutrient_magnesium_product_id' => ['nullable', 'integer', 'exists:nutrient_products,id'],
            'nutrient_micro_product_id' => ['nullable', 'integer', 'exists:nutrient_products,id'],
            'nutrient_dose_delay_sec' => ['nullable', 'integer', 'min:0', 'max:3600'],
            'nutrient_ec_stop_tolerance' => ['nullable', 'numeric', 'min:0', 'max:5'],
            'nutrient_solution_volume_l' => ['nullable', 'numeric', 'min:0.1', 'max:100000'],
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
        $this->validateNutritionRatioSum($data, $recipeRevisionPhase);

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

    /**
     * Проверяет, что доли NPK/Calcium/Magnesium/Micro заполнены и суммарно дают 100%.
     * Для PATCH учитывает уже сохранённые значения фазы.
     */
    private function validateNutritionRatioSum(array $data, ?RecipeRevisionPhase $existingPhase = null): void
    {
        $hasAnyIncomingRatio = array_key_exists('nutrient_npk_ratio_pct', $data)
            || array_key_exists('nutrient_calcium_ratio_pct', $data)
            || array_key_exists('nutrient_magnesium_ratio_pct', $data)
            || array_key_exists('nutrient_micro_ratio_pct', $data);

        $npk = $data['nutrient_npk_ratio_pct'] ?? $existingPhase?->nutrient_npk_ratio_pct;
        $calcium = $data['nutrient_calcium_ratio_pct'] ?? $existingPhase?->nutrient_calcium_ratio_pct;
        $magnesium = $data['nutrient_magnesium_ratio_pct'] ?? $existingPhase?->nutrient_magnesium_ratio_pct;
        $micro = $data['nutrient_micro_ratio_pct'] ?? $existingPhase?->nutrient_micro_ratio_pct;

        $hasAnyRatio = $npk !== null || $calcium !== null || $magnesium !== null || $micro !== null;

        if (! $hasAnyIncomingRatio && ! $hasAnyRatio) {
            return;
        }

        $validator = Validator::make([
            'nutrient_npk_ratio_pct' => $npk,
            'nutrient_calcium_ratio_pct' => $calcium,
            'nutrient_magnesium_ratio_pct' => $magnesium,
            'nutrient_micro_ratio_pct' => $micro,
        ], [
            'nutrient_npk_ratio_pct' => ['nullable', 'numeric', 'min:0', 'max:100'],
            'nutrient_calcium_ratio_pct' => ['nullable', 'numeric', 'min:0', 'max:100'],
            'nutrient_magnesium_ratio_pct' => ['nullable', 'numeric', 'min:0', 'max:100'],
            'nutrient_micro_ratio_pct' => ['nullable', 'numeric', 'min:0', 'max:100'],
        ]);

        $validator->after(function ($validator) use ($npk, $calcium, $magnesium, $micro): void {
            if ($npk === null || $calcium === null || $magnesium === null || $micro === null) {
                $validator->errors()->add(
                    'nutrient_ratio_components',
                    'Для питания обязательны все 4 доли: nutrient_npk_ratio_pct, nutrient_calcium_ratio_pct, nutrient_magnesium_ratio_pct, nutrient_micro_ratio_pct.'
                );

                return;
            }

            $sum = (float) ($npk ?? 0) + (float) ($calcium ?? 0) + (float) ($magnesium ?? 0) + (float) ($micro ?? 0);
            if (abs($sum - 100.0) > 0.01) {
                $validator->errors()->add(
                    'nutrient_ratio_sum',
                    'Сумма nutrient_npk_ratio_pct + nutrient_calcium_ratio_pct + nutrient_magnesium_ratio_pct + nutrient_micro_ratio_pct должна быть 100%.'
                );
            }
        });

        $validator->validate();
    }
}
