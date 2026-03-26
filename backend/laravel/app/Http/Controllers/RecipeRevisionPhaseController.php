<?php

namespace App\Http\Controllers;

use App\Models\RecipeRevision;
use App\Models\RecipeRevisionPhase;
use App\Services\RecipeRevisionPhaseService;
use App\Support\Recipes\RecipePhasePresenter;
use App\Support\Recipes\RecipePhasePayloadNormalizer;
use App\Support\Recipes\RecipePhaseRules;
use App\Support\Recipes\RecipePhaseTargetValidator;
use Illuminate\Http\JsonResponse;
use Illuminate\Http\Request;
use Illuminate\Support\Facades\Log;
use Illuminate\Support\Facades\Validator;
use Symfony\Component\HttpFoundation\Response;

class RecipeRevisionPhaseController extends Controller
{
    public function __construct(
        private RecipeRevisionPhaseService $phaseService,
        private RecipePhasePresenter $phasePresenter,
        private RecipePhasePayloadNormalizer $payloadNormalizer,
        private RecipePhaseTargetValidator $targetValidator,
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

        $data = $request->validate(RecipePhaseRules::store());
        $data = $this->payloadNormalizer->normalizeForWrite($data);
        $this->targetValidator->validateForStore($data);
        $this->validateNutritionRatioSum($data);

        try {
            $phase = $this->phaseService->createPhase($recipeRevision, $data);

            return response()->json([
                'status' => 'ok',
                'data' => $this->phasePresenter->present($phase->load('stageTemplate')),
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

        $data = $request->validate(RecipePhaseRules::update());
        $data = $this->payloadNormalizer->normalizeForWrite($data);
        $this->targetValidator->validateForUpdate($data, $recipeRevisionPhase);
        $this->validateNutritionRatioSum($data, $recipeRevisionPhase);

        try {
            $phase = $this->phaseService->updatePhase($recipeRevisionPhase, $data);

            return response()->json([
                'status' => 'ok',
                'data' => $this->phasePresenter->present($phase),
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
