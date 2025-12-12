<?php

namespace App\Http\Controllers;

use App\Models\Recipe;
use App\Models\RecipeStageMap;
use App\Helpers\ZoneAccessHelper;
use Illuminate\Http\JsonResponse;
use Illuminate\Http\Request;
use Illuminate\Support\Facades\DB;
use Symfony\Component\HttpFoundation\Response;

class RecipeStageMapController extends Controller
{
    /**
     * Получить stage-map для рецепта
     * GET /api/recipes/{id}/stage-map
     */
    public function show(Request $request, Recipe $recipe): JsonResponse
    {
        $user = $request->user();
        if (!$user) {
            return response()->json([
                'status' => 'error',
                'message' => 'Unauthorized',
            ], 401);
        }

        $stageMaps = $recipe->stageMaps()
            ->with('stageTemplate')
            ->orderBy('order_index')
            ->get();

        // Если stage-map нет, создаем автоматически
        if ($stageMaps->isEmpty()) {
            $growCycleService = app(\App\Services\GrowCycleService::class);
            $growCycleService->ensureRecipeStageMap($recipe);
            $stageMaps = $recipe->stageMaps()
                ->with('stageTemplate')
                ->orderBy('order_index')
                ->get();
        }

        return response()->json([
            'status' => 'ok',
            'data' => $stageMaps->map(function ($map) {
                return [
                    'id' => $map->id,
                    'stage_template' => [
                        'id' => $map->stageTemplate->id,
                        'name' => $map->stageTemplate->name,
                        'code' => $map->stageTemplate->code,
                        'ui_meta' => $map->stageTemplate->ui_meta,
                    ],
                    'order_index' => $map->order_index,
                    'start_offset_days' => $map->start_offset_days,
                    'end_offset_days' => $map->end_offset_days,
                    'phase_indices' => $map->phase_indices,
                    'targets_override' => $map->targets_override,
                ];
            }),
        ]);
    }

    /**
     * Обновить stage-map для рецепта
     * PUT /api/recipes/{id}/stage-map
     */
    public function update(Request $request, Recipe $recipe): JsonResponse
    {
        $user = $request->user();
        if (!$user) {
            return response()->json([
                'status' => 'error',
                'message' => 'Unauthorized',
            ], 401);
        }

        // Проверяем права (только operator+)
        if (!in_array($user->role, ['operator', 'admin', 'agronomist'])) {
            return response()->json([
                'status' => 'error',
                'message' => 'Forbidden',
            ], 403);
        }

        $data = $request->validate([
            'stages' => ['required', 'array'],
            'stages.*.stage_template_id' => ['required', 'integer', 'exists:grow_stage_templates,id'],
            'stages.*.order_index' => ['required', 'integer', 'min:0'],
            'stages.*.start_offset_days' => ['nullable', 'integer', 'min:0'],
            'stages.*.end_offset_days' => ['nullable', 'integer', 'min:0'],
            'stages.*.phase_indices' => ['nullable', 'array'],
            'stages.*.phase_indices.*' => ['integer'],
            'stages.*.targets_override' => ['nullable', 'array'],
        ]);

        return DB::transaction(function () use ($recipe, $data) {
            // Удаляем существующие маппинги
            $recipe->stageMaps()->delete();

            // Создаем новые маппинги
            foreach ($data['stages'] as $stageData) {
                RecipeStageMap::create([
                    'recipe_id' => $recipe->id,
                    'stage_template_id' => $stageData['stage_template_id'],
                    'order_index' => $stageData['order_index'],
                    'start_offset_days' => $stageData['start_offset_days'] ?? null,
                    'end_offset_days' => $stageData['end_offset_days'] ?? null,
                    'phase_indices' => $stageData['phase_indices'] ?? [],
                    'targets_override' => $stageData['targets_override'] ?? null,
                ]);
            }

            // Возвращаем обновленный stage-map
            $stageMaps = $recipe->stageMaps()
                ->with('stageTemplate')
                ->orderBy('order_index')
                ->get();

            return response()->json([
                'status' => 'ok',
                'data' => $stageMaps->map(function ($map) {
                    return [
                        'id' => $map->id,
                        'stage_template' => [
                            'id' => $map->stageTemplate->id,
                            'name' => $map->stageTemplate->name,
                            'code' => $map->stageTemplate->code,
                            'ui_meta' => $map->stageTemplate->ui_meta,
                        ],
                        'order_index' => $map->order_index,
                        'start_offset_days' => $map->start_offset_days,
                        'end_offset_days' => $map->end_offset_days,
                        'phase_indices' => $map->phase_indices,
                        'targets_override' => $map->targets_override,
                    ];
                }),
            ]);
        });
    }
}

