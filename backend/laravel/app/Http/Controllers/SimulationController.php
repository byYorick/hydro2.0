<?php

namespace App\Http\Controllers;

use App\Models\Zone;
use App\Models\ZoneSimulation;
use App\Models\TelemetryLast;
use App\Services\DigitalTwinService;
use Illuminate\Http\Request;
use Illuminate\Http\JsonResponse;

class SimulationController extends Controller
{
    public function __construct(
        private DigitalTwinService $digitalTwinService
    ) {
    }

    /**
     * POST /api/simulations/zone/{zone}
     * Запустить симуляцию зоны
     */
    public function simulateZone(Request $request, Zone $zone): JsonResponse
    {
        $validated = $request->validate([
            'scenario' => ['required', 'array'],
            'scenario.recipe_id' => ['required', 'integer', 'exists:recipes,id'],
            'scenario.initial_state' => ['nullable', 'array'],
            'scenario.initial_state.ph' => ['nullable', 'numeric'],
            'scenario.initial_state.ec' => ['nullable', 'numeric'],
            'scenario.initial_state.temp_air' => ['nullable', 'numeric'],
            'scenario.initial_state.temp_water' => ['nullable', 'numeric'],
            'scenario.initial_state.humidity_air' => ['nullable', 'numeric'],
            'duration_hours' => ['nullable', 'integer', 'min:1', 'max:720'], // до 30 дней
            'step_minutes' => ['nullable', 'integer', 'min:1', 'max:60'],
        ]);

        // Если initial_state не указан, используем текущие значения телеметрии
        if (!isset($validated['scenario']['initial_state'])) {
            $telemetry = TelemetryLast::query()
                ->where('zone_id', $zone->id)
                ->get()
                ->keyBy('metric_type');

            $validated['scenario']['initial_state'] = [
                'ph' => $telemetry->get('ph')?->value ?? 6.0,
                'ec' => $telemetry->get('ec')?->value ?? 1.2,
                'temp_air' => $telemetry->get('temp_air')?->value ?? 22.0,
                'temp_water' => $telemetry->get('temp_water')?->value ?? 20.0,
                'humidity_air' => $telemetry->get('humidity_air')?->value ?? 60.0,
            ];
        }

        $durationHours = $validated['duration_hours'] ?? 72;
        $stepMinutes = $validated['step_minutes'] ?? 10;

        $simulation = $this->digitalTwinService->simulateZone(
            $zone,
            $validated['scenario'],
            $durationHours,
            $stepMinutes
        );

        return response()->json([
            'status' => 'ok',
            'data' => [
                'simulation_id' => $simulation->id,
                'status' => $simulation->status,
                'results' => $simulation->results,
                'error_message' => $simulation->error_message,
            ],
        ], $simulation->status === 'completed' ? 200 : 202);
    }

    /**
     * GET /api/simulations/{simulation}
     * Получить результаты симуляции
     */
    public function show(ZoneSimulation $simulation): JsonResponse
    {
        return response()->json([
            'status' => 'ok',
            'data' => [
                'id' => $simulation->id,
                'zone_id' => $simulation->zone_id,
                'scenario' => $simulation->scenario,
                'results' => $simulation->results,
                'duration_hours' => $simulation->duration_hours,
                'step_minutes' => $simulation->step_minutes,
                'status' => $simulation->status,
                'error_message' => $simulation->error_message,
                'created_at' => $simulation->created_at->toIso8601String(),
            ],
        ]);
    }
}
