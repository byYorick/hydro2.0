<?php

namespace App\Http\Controllers;

use App\Models\TelemetryLast;
use App\Models\Command;
use App\Models\Zone;
use App\Models\ZoneEvent;
use App\Models\ZoneSimulation;
use App\Jobs\RunSimulationJob;
use Illuminate\Http\JsonResponse;
use Illuminate\Http\Request;
use Illuminate\Support\Carbon;
use Illuminate\Support\Arr;
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
            'full_simulation' => 'nullable|boolean',
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
        if (array_key_exists('full_simulation', $data)) {
            $scenario['full_simulation'] = (bool) $data['full_simulation'];
        }

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
                'full_simulation' => $data['full_simulation'] ?? false,
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
                $simMeta = $this->extractSimulationMeta($simulation);
                $payload['simulation'] = [
                    'id' => $simulation->id,
                    'status' => $simulation->status,
                    'duration_hours' => $simulation->duration_hours,
                    'step_minutes' => $simulation->step_minutes,
                    'engine' => $simMeta['engine'] ?? null,
                    'mode' => $simMeta['mode'] ?? null,
                    'orchestrator' => $simMeta['orchestrator'] ?? null,
                ];
                if ($simulation->relationLoaded('report')) {
                    $payload['report'] = $simulation->report;
                } else {
                    $payload['report'] = $simulation->report()->first();
                }
                $activity = $this->buildSimulationActivity($simulation, $simMeta);
                if ($activity) {
                    $payload = array_merge($payload, $activity);
                }
                $progress = $this->buildSimulationProgress(
                    $simulation,
                    $payload,
                    $simMeta,
                    $activity['last_action_at'] ?? null,
                );
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

    private function buildSimulationProgress(
        ZoneSimulation $simulation,
        array $payload,
        array $simMeta,
        ?string $lastActionAt,
    ): ?array
    {
        $realDurationMinutes = $simMeta['real_duration_minutes'] ?? ($payload['sim_duration_minutes'] ?? null);
        if (!is_numeric($realDurationMinutes) || (float) $realDurationMinutes <= 0) {
            return null;
        }

        $realStartedAt = $this->resolveRealStartedAt($simulation, $simMeta, $payload);
        if (! $realStartedAt) {
            return null;
        }

        $realStarted = Carbon::parse($realStartedAt);
        $anchorTime = $simulation->status === 'running' ? now() : ($lastActionAt ? Carbon::parse($lastActionAt) : now());
        $elapsedSeconds = $realStarted->greaterThan($anchorTime) ? 0 : $realStarted->diffInSeconds($anchorTime);
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
            'progress_source' => $simulation->status === 'running' ? 'timer' : ($lastActionAt ? 'actions' : 'timer'),
        ];
    }

    private function buildSimulationActivity(ZoneSimulation $simulation, array $simMeta): ?array
    {
        $realStartedAt = $this->resolveRealStartedAt($simulation, $simMeta, []);
        if (! $realStartedAt) {
            return null;
        }

        $realStarted = Carbon::parse($realStartedAt);
        $zoneId = $simulation->zone_id;

        $events = ZoneEvent::query()
            ->where('zone_id', $zoneId)
            ->where('created_at', '>=', $realStarted)
            ->where(function ($query) {
                $query->whereIn('type', [
                    'PHASE_CHANGE',
                    'PHASE_TRANSITION',
                    'IRRIGATION_START',
                    'IRRIGATION_STOP',
                    'IRRIGATION_STARTED',
                    'IRRIGATION_FINISHED',
                    'RECIPE_STARTED',
                    'PID_OUTPUT',
                    'command_status',
                    'alert_created',
                    'alert_updated',
                ])
                    ->orWhere('type', 'like', 'CYCLE_%')
                    ->orWhere('type', 'like', 'STAGE_%');
            })
            ->orderByDesc('created_at')
            ->limit(15)
            ->get();

        $commands = Command::query()
            ->where('zone_id', $zoneId)
            ->where('created_at', '>=', $realStarted)
            ->with(['node:id,uid'])
            ->orderByDesc('created_at')
            ->limit(10)
            ->get();

        $actions = [];
        foreach ($commands as $command) {
            $actions[] = [
                'ts' => $command->created_at?->getTimestamp(),
                'kind' => 'command',
                'id' => $command->id,
                'summary' => trim(sprintf(
                    '%s %s %s',
                    $command->cmd,
                    $command->channel ?? '',
                    $command->status ?? ''
                )),
                'cmd' => $command->cmd,
                'status' => $command->status,
                'channel' => $command->channel,
                'node_uid' => $command->node?->uid,
                'created_at' => $command->created_at?->toIso8601String(),
            ];
        }

        $currentPhase = null;
        foreach ($events as $event) {
            $details = $event->details ?? [];
            if (in_array($event->type, ['PHASE_CHANGE', 'PHASE_TRANSITION'], true)) {
                $currentPhase = $details['phase_name'] ?? $details['to_phase'] ?? $details['phase_index'] ?? null;
            }
            if (! $currentPhase && isset($details['phase_name'])) {
                $currentPhase = $details['phase_name'];
            }

            $actions[] = [
                'ts' => $event->created_at?->getTimestamp(),
                'kind' => 'event',
                'id' => $event->id,
                'summary' => $this->formatEventSummary($event->type, $details),
                'event_type' => $event->type,
                'details' => $details,
                'created_at' => $event->created_at?->toIso8601String(),
            ];
        }

        $sortedActions = collect($actions)
            ->filter(fn ($action) => isset($action['ts']))
            ->sortByDesc('ts')
            ->values()
            ->take(6)
            ->map(fn ($action) => Arr::except($action, ['ts']))
            ->all();

        $lastActionAt = $sortedActions[0]['created_at'] ?? null;

        $pidStatuses = $this->buildPidStatuses($events, $zoneId, $realStarted);

        return [
            'actions' => $sortedActions,
            'last_action_at' => $lastActionAt,
            'current_phase' => $currentPhase,
            'pid_statuses' => $pidStatuses,
        ];
    }

    private function buildPidStatuses($events, int $zoneId, Carbon $realStarted): array
    {
        $pidEvents = $events->where('type', 'PID_OUTPUT');

        if ($pidEvents->isEmpty()) {
            $pidEvents = ZoneEvent::query()
                ->where('zone_id', $zoneId)
                ->where('type', 'PID_OUTPUT')
                ->where('created_at', '>=', $realStarted)
                ->orderByDesc('created_at')
                ->limit(20)
                ->get();
        }

        $statuses = [];
        foreach ($pidEvents as $event) {
            $details = $event->details ?? [];
            $type = $details['type'] ?? null;
            if (! $type || isset($statuses[$type])) {
                continue;
            }

            $statuses[$type] = [
                'type' => $type,
                'current' => $details['current'] ?? null,
                'target' => $details['target'] ?? null,
                'output' => $details['output'] ?? null,
                'zone_state' => $details['zone_state'] ?? null,
                'error' => $details['error'] ?? null,
                'safety_skip_reason' => $details['safety_skip_reason'] ?? null,
                'updated_at' => $event->created_at?->toIso8601String(),
            ];
        }

        return array_values($statuses);
    }

    private function formatEventSummary(string $type, array $details): string
    {
        if (str_starts_with($type, 'CYCLE_') || str_starts_with($type, 'STAGE_')) {
            $action = $details['action'] ?? $type;
            $label = strtolower(str_replace('_', ' ', (string) $action));
            $phase = $details['phase_name'] ?? $details['stage_code'] ?? null;
            $suffix = $phase ? " ({$phase})" : '';

            return "Цикл: {$label}{$suffix}";
        }

        return match ($type) {
            'PHASE_CHANGE', 'PHASE_TRANSITION' => 'Фаза: '.($details['phase_name'] ?? $details['to_phase'] ?? $details['phase_index'] ?? $type),
            'IRRIGATION_START', 'IRRIGATION_STARTED', 'IRRIGATION_STOP', 'IRRIGATION_FINISHED' => $this->formatIrrigationSummary($type, $details),
            'RECIPE_STARTED' => 'Рецепт: старт',
            'PID_OUTPUT' => $this->formatPidSummary($details),
            'command_status' => 'Статус команды: '.($details['status'] ?? 'update'),
            'alert_created' => 'Алерт: '.($details['code'] ?? 'created'),
            'alert_updated' => 'Алерт: '.($details['code'] ?? 'updated'),
            default => $type,
        };
    }

    private function formatPidType(?string $type): string
    {
        if (! $type) {
            return 'unknown';
        }

        return strtoupper($type);
    }

    private function formatPidSummary(array $details): string
    {
        $pidType = $this->formatPidType($details['type'] ?? null);
        $current = $this->formatNumber($details['current'] ?? null, 2);
        $target = $this->formatNumber($details['target'] ?? null, 2);
        $output = $this->formatNumber($details['output'] ?? null, 2);
        $zone = $details['zone_state'] ?? null;
        $dt = $this->formatNumber($details['dt_seconds'] ?? null, 1);
        $skip = $details['safety_skip_reason'] ?? null;

        $parts = ["PID {$pidType}"];
        if ($current !== null && $target !== null) {
            $parts[] = "{$current}→{$target}";
        }
        if ($output !== null) {
            $parts[] = "out={$output}";
        }
        if ($zone) {
            $parts[] = "zone={$zone}";
        }
        if ($dt !== null) {
            $parts[] = "dt={$dt}s";
        }
        if ($skip) {
            $parts[] = "skip={$skip}";
        }

        return implode(' ', $parts);
    }

    private function formatIrrigationSummary(string $type, array $details): string
    {
        $isStart = in_array($type, ['IRRIGATION_START', 'IRRIGATION_STARTED'], true);
        $label = $isStart ? 'Полив: старт' : 'Полив: стоп';

        $durationSec = $this->formatNumber($details['duration_sec'] ?? null, 1);
        if ($durationSec === null && is_numeric($details['duration_ms'] ?? null)) {
            $durationSec = $this->formatNumber(((float) $details['duration_ms']) / 1000, 1);
        }
        $actualDuration = $this->formatNumber($details['actual_duration_sec'] ?? null, 1);
        $volumeLiters = $this->formatNumber($details['volume_l'] ?? null, 2);
        $totalMl = $this->formatNumber($details['total_ml'] ?? null, 1);
        $flow = $this->formatNumber($details['flow_rate'] ?? $details['flow_value'] ?? null, 2);
        $nodes = is_numeric($details['nodes_count'] ?? null) ? (string) (int) $details['nodes_count'] : null;

        $parts = [$label];
        if ($durationSec !== null) {
            $parts[] = "dur={$durationSec}s";
        }
        if ($actualDuration !== null) {
            $parts[] = "actual={$actualDuration}s";
        }
        if ($volumeLiters !== null) {
            $parts[] = "vol={$volumeLiters}L";
        } elseif ($totalMl !== null) {
            $parts[] = "vol={$totalMl}ml";
        }
        if ($flow !== null) {
            $parts[] = "flow={$flow}";
        }
        if ($nodes) {
            $parts[] = "nodes={$nodes}";
        }

        return implode(' ', $parts);
    }

    private function formatNumber(mixed $value, int $precision = 2): ?string
    {
        if ($value === null || $value === '') {
            return null;
        }
        if (! is_numeric($value)) {
            return null;
        }

        return number_format((float) $value, $precision, '.', '');
    }

    private function extractSimulationMeta(ZoneSimulation $simulation): array
    {
        $scenario = $simulation->scenario ?? [];
        if (! is_array($scenario)) {
            return [];
        }

        $simMeta = $scenario['simulation'] ?? null;
        if (! is_array($simMeta)) {
            return [];
        }

        return $simMeta;
    }

    private function resolveRealStartedAt(ZoneSimulation $simulation, array $simMeta, array $payload): ?string
    {
        $realStartedAt = $simMeta['real_started_at'] ?? ($payload['started_at'] ?? null);
        if (! $realStartedAt) {
            $realStartedAt = $simulation->created_at?->toIso8601String();
        }

        return $realStartedAt ?: null;
    }
}
