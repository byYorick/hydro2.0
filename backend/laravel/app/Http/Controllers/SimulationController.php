<?php

namespace App\Http\Controllers;

use App\Models\Zone;
use App\Jobs\RunSimulationJob;
use Illuminate\Http\Request;
use Illuminate\Http\JsonResponse;
use Illuminate\Validation\ValidationException;
use Illuminate\Support\Facades\Cache;
use Illuminate\Support\Str;

class SimulationController extends Controller
{
    /**
     * Симулировать зону (асинхронно через очередь).
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

        // Генерируем уникальный ID для job
        $jobId = 'sim_' . Str::uuid()->toString();

        // Создаем job и отправляем в очередь
        RunSimulationJob::dispatch(
            $zone->id,
            [
                'duration_hours' => $data['duration_hours'] ?? 72,
                'step_minutes' => $data['step_minutes'] ?? 10,
                'scenario' => $scenario,
            ],
            $jobId
        );

        // Устанавливаем начальный статус
        Cache::put("simulation:{$jobId}", [
            'status' => 'queued',
            'created_at' => now()->toIso8601String(),
        ], 3600);

        return response()->json([
            'status' => 'ok',
            'data' => [
                'job_id' => $jobId,
                'status' => 'queued',
                'message' => 'Simulation queued successfully. Use GET /api/simulations/{job_id} to check status.',
            ],
        ], 202); // 202 Accepted
    }

    /**
     * Получить статус симуляции.
     *
     * @param Request $request
     * @param string $jobId
     * @return JsonResponse
     */
    public function show(Request $request, string $jobId): JsonResponse
    {
        $status = Cache::get("simulation:{$jobId}");

        if (!$status) {
            return response()->json([
                'status' => 'error',
                'code' => 'NOT_FOUND',
                'message' => 'Simulation job not found or expired.',
            ], 404);
        }

        return response()->json([
            'status' => 'ok',
            'data' => $status,
        ]);
    }
}
