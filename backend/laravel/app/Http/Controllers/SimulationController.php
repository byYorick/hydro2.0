<?php

namespace App\Http\Controllers;

use App\Models\TelemetryLast;
use App\Models\Zone;
use App\Models\ZoneSimulation;
use App\Jobs\RunSimulationJob;
use Illuminate\Http\JsonResponse;
use Illuminate\Http\Request;
use Illuminate\Support\Carbon;
use Illuminate\Support\Facades\Cache;
use Illuminate\Support\Str;
use Illuminate\Validation\ValidationException;

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
            'sim_duration_minutes' => 'nullable|integer|min:1|max:10080',
        ]);

        // Формируем сценарий
        // Получаем recipe_id из активного GrowCycle, если не указан явно
        $recipeId = $data['recipe_id'] ?? null;
        if (!$recipeId) {
            $zone->load('activeGrowCycle.recipeRevision');
            if ($zone->activeGrowCycle && $zone->activeGrowCycle->recipeRevision) {
                $recipeId = $zone->activeGrowCycle->recipeRevision->recipe_id;
            }
        }
        
        $scenario = [
            'recipe_id' => $recipeId,
            'initial_state' => $data['initial_state'] ?? [],
        ];

        // Если initial_state пустой, получаем текущее состояние зоны из telemetry_last
        if (empty($scenario['initial_state'])) {
            $telemetry = TelemetryLast::query()
                ->join('sensors', 'telemetry_last.sensor_id', '=', 'sensors.id')
                ->where('sensors.zone_id', $zone->id)
                ->whereNotNull('sensors.zone_id')
                ->whereIn('sensors.type', ['PH', 'EC', 'TEMPERATURE', 'HUMIDITY'])
                ->select([
                    'sensors.type as metric_type',
                    'sensors.label as channel',
                    'telemetry_last.last_value as value'
                ])
                ->get()
                ->mapWithKeys(function ($item) {
                    $key = strtolower($item->channel ?? $item->metric_type ?? '');
                    if ($key === '') {
                        return [];
                    }
                    return [$key => $item->value];
                })
                ->toArray();

            // Используем значения из телеметрии или дефолтные значения
            $scenario['initial_state'] = [
                'ph' => $telemetry['ph'] ?? 6.0,
                'ec' => $telemetry['ec'] ?? 1.2,
                'temp_air' => $telemetry['temp_air'] ?? $telemetry['temperature'] ?? 22.0,
                'temp_water' => $telemetry['temp_water'] ?? $telemetry['temperature'] ?? 20.0,
                'humidity_air' => $telemetry['humidity_air'] ?? $telemetry['humidity'] ?? 60.0,
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
                'sim_duration_minutes' => $data['sim_duration_minutes'] ?? null,
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

        $payload = $status;
        $simulationId = $status['simulation_id'] ?? null;
        if ($simulationId) {
            $simulation = ZoneSimulation::find($simulationId);
            if ($simulation) {
                $payload['simulation'] = [
                    'id' => $simulation->id,
                    'status' => $simulation->status,
                    'duration_hours' => $simulation->duration_hours,
                    'step_minutes' => $simulation->step_minutes,
                ];
                $progress = $this->buildSimulationProgress($simulation, $payload);
                if ($progress) {
                    $payload = array_merge($payload, $progress);
                }
            }
        }

        return response()->json([
            'status' => 'ok',
            'data' => $payload,
        ]);
    }

    private function buildSimulationProgress(ZoneSimulation $simulation, array $payload): ?array
    {
        $scenario = $simulation->scenario ?? [];
        $simMeta = [];
        if (is_array($scenario) && isset($scenario['simulation']) && is_array($scenario['simulation'])) {
            $simMeta = $scenario['simulation'];
        }

        $realDurationMinutes = $simMeta['real_duration_minutes'] ?? ($payload['sim_duration_minutes'] ?? null);
        if (!is_numeric($realDurationMinutes) || (float) $realDurationMinutes <= 0) {
            return null;
        }

        $realStartedAt = $simMeta['real_started_at'] ?? ($payload['started_at'] ?? null);
        if (!$realStartedAt) {
            $realStartedAt = $simulation->created_at?->toIso8601String();
        }
        if (!$realStartedAt) {
            return null;
        }

        $realStarted = Carbon::parse($realStartedAt);
        $now = now();
        $elapsedSeconds = $realStarted->greaterThan($now) ? 0 : $realStarted->diffInSeconds($now);
        $elapsedMinutes = $elapsedSeconds / 60;
        $progress = min(1.0, $elapsedMinutes / (float) $realDurationMinutes);
        if ($simulation->status === 'completed') {
            $progress = 1.0;
        }

        $simNow = null;
        $timeScale = $simMeta['time_scale'] ?? null;
        $simStartedAt = $simMeta['sim_started_at'] ?? null;
        if ($simStartedAt && is_numeric($timeScale)) {
            $simNow = Carbon::parse($simStartedAt)
                ->addSeconds($elapsedSeconds * (float) $timeScale)
                ->toIso8601String();
        }

        return [
            'progress' => round($progress, 4),
            'elapsed_minutes' => round(min($elapsedMinutes, (float) $realDurationMinutes), 2),
            'real_duration_minutes' => (int) $realDurationMinutes,
            'sim_now' => $simNow,
        ];
    }
}
