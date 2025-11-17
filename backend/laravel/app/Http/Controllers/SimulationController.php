<?php

namespace App\Http\Controllers;

use App\Models\Zone;
use App\Services\DigitalTwinClient;
use Illuminate\Http\Request;
use Illuminate\Http\JsonResponse;
use Illuminate\Validation\ValidationException;

class SimulationController extends Controller
{
    public function __construct(
        private DigitalTwinClient $client
    ) {
    }

    /**
     * Симулировать зону.
     *
     * @param Request $request
     * @param Zone $zone
     * @return JsonResponse
     * @throws ValidationException
     */
    public function simulateZone(Request $request, Zone $zone): JsonResponse
    {
        $data = $request->validate([
            'duration_hours' => 'integer|min:1|max:720',
            'step_minutes' => 'integer|min:1|max:60',
            'initial_state' => 'array',
            'recipe_id' => 'nullable|exists:recipes,id',
        ]);

        // Формируем сценарий
        // Получаем recipe_id из ZoneRecipeInstance, если не указан явно
        $recipeId = $data['recipe_id'] ?? null;
        if (!$recipeId) {
            $zone->load('recipeInstance');
            if ($zone->recipeInstance) {
                $recipeId = $zone->recipeInstance->recipe_id;
            }
        }
        
        $scenario = [
            'recipe_id' => $recipeId,
            'initial_state' => $data['initial_state'] ?? [],
        ];

        // Если initial_state пустой, можно попробовать получить текущее состояние зоны
        if (empty($scenario['initial_state'])) {
            // TODO: Получить текущее состояние из telemetry_last
            // Пока используем дефолтные значения
            $scenario['initial_state'] = [
                'ph' => 6.0,
                'ec' => 1.2,
                'temp_air' => 22.0,
                'temp_water' => 20.0,
                'humidity_air' => 60.0,
            ];
        }

        try {
            $result = $this->client->simulateZone($zone->id, [
                'duration_hours' => $data['duration_hours'] ?? 72,
                'step_minutes' => $data['step_minutes'] ?? 10,
                'scenario' => $scenario,
            ]);

            return response()->json($result);
        } catch (\Exception $e) {
            return response()->json([
                'status' => 'error',
                'message' => $e->getMessage(),
            ], 500);
        }
    }
}
