<?php

namespace App\Jobs;

use App\Models\ZoneSimulation;
use App\Services\DigitalTwinClient;
use App\Services\SimulationOrchestratorService;
use App\Models\Zone;
use Illuminate\Bus\Queueable;
use Illuminate\Contracts\Queue\ShouldQueue;
use Illuminate\Foundation\Bus\Dispatchable;
use Illuminate\Queue\InteractsWithQueue;
use Illuminate\Queue\SerializesModels;
use Illuminate\Support\Facades\Cache;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Log;

class RunSimulationJob implements ShouldQueue
{
    use Dispatchable, InteractsWithQueue, Queueable, SerializesModels;

    public int $timeout = 600; // 10 минут на выполнение job

    /**
     * Create a new job instance.
     */
    public function __construct(
        public int $zoneId,
        public array $params,
        public string $jobId
    ) {
        //
    }

    /**
     * Execute the job.
     */
    public function handle(DigitalTwinClient $client, SimulationOrchestratorService $orchestrator): void
    {
        $simulation = null;
        $simulationId = null;
        try {
            $durationHours = $this->params['duration_hours'] ?? 72;
            $stepMinutes = $this->params['step_minutes'] ?? 10;
            $scenario = is_array($this->params['scenario'] ?? null)
                ? $this->params['scenario']
                : [];
            $simDurationMinutes = $this->params['sim_duration_minutes'] ?? null;
            $isLiveSimulation = is_numeric($simDurationMinutes) && (int) $simDurationMinutes > 0;
            $fullSimulation = (bool) ($this->params['full_simulation'] ?? ($scenario['full_simulation'] ?? false));

            $nowIso = now()->toIso8601String();
            $simulationMeta = [
                'real_started_at' => $nowIso,
                'sim_started_at' => $nowIso,
                'engine' => $isLiveSimulation ? 'pipeline' : 'digital_twin',
                'mode' => $isLiveSimulation ? 'live' : 'model',
            ];
            if ($isLiveSimulation) {
                $timeScale = ($durationHours * 60) / (int) $simDurationMinutes;
                $simulationMeta['real_duration_minutes'] = (int) $simDurationMinutes;
                $simulationMeta['time_scale'] = $timeScale;
                $simulationMeta['orchestrator'] = 'digital-twin';
            }

            $existingMeta = [];
            if (isset($scenario['simulation']) && is_array($scenario['simulation'])) {
                $existingMeta = $scenario['simulation'];
            }
            $scenario['simulation'] = array_merge($existingMeta, $simulationMeta);
            $scenarioPayload = $scenario;
            unset($scenarioPayload['simulation']);

            if ($isLiveSimulation) {
                $sourceZone = Zone::findOrFail($this->zoneId);
                $recipeId = $scenario['recipe_id'] ?? null;
                if (! $recipeId && ! $fullSimulation) {
                    $fullSimulation = true;
                }
                $context = $orchestrator->createSimulationContext(
                    $sourceZone,
                    $recipeId ? (int) $recipeId : null,
                    ['full_simulation' => $fullSimulation]
                );
                $simZone = $context['zone'];
                $simCycle = $context['grow_cycle'];
                $createdRecipe = $context['recipe'] ?? null;
                if ($createdRecipe) {
                    $recipeId = $createdRecipe->id;
                }
                if (! $recipeId) {
                    throw new \RuntimeException('recipe_id required for live simulation.');
                }
                $scenario['recipe_id'] = $recipeId;

                $scenario['simulation'] = array_merge(
                    $scenario['simulation'] ?? [],
                    [
                        'source_zone_id' => $this->zoneId,
                        'sim_zone_id' => $simZone->id,
                        'sim_grow_cycle_id' => $simCycle->id,
                        'full_simulation' => $fullSimulation,
                        'created_plant_id' => $context['plant']?->id,
                        'created_recipe_id' => $context['recipe']?->id,
                        'created_recipe_revision_id' => $context['recipe_revision']?->id,
                        'created_node_id' => $context['node']?->id,
                        'created_node_uid' => $context['node']?->uid,
                    ]
                );

                $startResponse = $client->startLiveSimulation([
                    'zone_id' => $simZone->id,
                    'duration_hours' => $durationHours,
                    'step_minutes' => $stepMinutes,
                    'sim_duration_minutes' => (int) $simDurationMinutes,
                    'scenario' => $scenario,
                ]);
                $simulationId = $startResponse['simulation_id'] ?? null;

                Cache::put("simulation:{$this->jobId}", [
                    'status' => 'processing',
                    'started_at' => now()->toIso8601String(),
                    'simulation_id' => $simulationId,
                    'sim_duration_minutes' => (int) $simDurationMinutes,
                    'simulation_zone_id' => $simZone->id,
                    'simulation_grow_cycle_id' => $simCycle->id,
                ], 3600);

                if ($simulationId) {
                    $this->recordSimulationEvent(
                        $simulationId,
                        $simZone->id,
                        'laravel',
                        'live_start',
                        'completed',
                        'Live-симуляция запущена',
                        [
                            'source_zone_id' => $this->zoneId,
                            'simulation_zone_id' => $simZone->id,
                            'simulation_grow_cycle_id' => $simCycle->id,
                            'full_simulation' => $fullSimulation,
                            'job_id' => $this->jobId,
                        ]
                    );
                }

                Log::info('Live simulation started via digital-twin', [
                    'job_id' => $this->jobId,
                    'zone_id' => $this->zoneId,
                    'simulation_zone_id' => $simZone->id,
                    'simulation_id' => $simulationId,
                ]);

                if ($simulationId && $fullSimulation) {
                    $simulation = $this->resolveSimulation($simulationId);
                    if ($simulation) {
                        $orchestrator->executeFullSimulation($simulation, $context);
                    }
                }

                return;
            }

            $simulation = ZoneSimulation::create([
                'zone_id' => $this->zoneId,
                'scenario' => $scenario,
                'duration_hours' => $durationHours,
                'step_minutes' => $stepMinutes,
                'status' => 'running',
            ]);
            $simulationId = $simulation->id;

            $this->recordSimulationEvent(
                $simulationId,
                $this->zoneId,
                'laravel',
                'job',
                'running',
                'Симуляция запущена',
                [
                    'job_id' => $this->jobId,
                ]
            );

            // Устанавливаем статус "processing"
            Cache::put("simulation:{$this->jobId}", [
                'status' => 'processing',
                'started_at' => now()->toIso8601String(),
                'simulation_id' => $simulation->id,
                'sim_duration_minutes' => null,
            ], 3600); // Храним 1 час

            // Выполняем симуляцию
            $result = $client->simulateZone($this->zoneId, [
                'duration_hours' => $durationHours,
                'step_minutes' => $stepMinutes,
                'scenario' => $scenarioPayload,
            ]);

            // Сохраняем результат
            $simulation->update([
                'status' => 'completed',
                'results' => $result['data'] ?? null,
            ]);
            $this->recordSimulationEvent(
                $simulationId,
                $this->zoneId,
                'laravel',
                'job',
                'completed',
                'Симуляция завершена',
                [
                    'job_id' => $this->jobId,
                ]
            );
            Cache::put("simulation:{$this->jobId}", [
                'status' => 'completed',
                'result' => $result,
                'completed_at' => now()->toIso8601String(),
                'simulation_id' => $simulation->id,
            ], 3600);

            Log::info('Simulation job completed', [
                'job_id' => $this->jobId,
                'zone_id' => $this->zoneId,
            ]);
        } catch (\Exception $e) {
            // Сохраняем ошибку
            if ($simulation) {
                $simulation->update([
                    'status' => 'failed',
                    'error_message' => $e->getMessage(),
                ]);
            }
            if ($simulationId) {
                $this->recordSimulationEvent(
                    $simulationId,
                    $this->zoneId,
                    'laravel',
                    'job',
                    'failed',
                    'Симуляция завершилась ошибкой',
                    [
                        'job_id' => $this->jobId,
                        'error' => $e->getMessage(),
                    ],
                    'error'
                );
            }
            Cache::put("simulation:{$this->jobId}", [
                'status' => 'failed',
                'error' => $e->getMessage(),
                'failed_at' => now()->toIso8601String(),
                'simulation_id' => $simulation?->id,
            ], 3600);

            Log::error('Simulation job failed', [
                'job_id' => $this->jobId,
                'zone_id' => $this->zoneId,
                'error' => $e->getMessage(),
                'exception' => get_class($e),
            ]);

            // In testing environment, don't throw exceptions to avoid affecting HTTP responses
            if (! app()->environment('testing')) {
                throw $e; // Пробрасываем для retry механизма
            }
        }
    }

    private function recordSimulationEvent(
        int $simulationId,
        int $zoneId,
        string $service,
        string $stage,
        string $status,
        string $message,
        array $payload = [],
        string $level = 'info',
    ): void {
        try {
            DB::table('simulation_events')->insert([
                'simulation_id' => $simulationId,
                'zone_id' => $zoneId,
                'service' => $service,
                'stage' => $stage,
                'status' => $status,
                'level' => $level,
                'message' => $message,
                'payload' => $payload ? json_encode($payload, JSON_UNESCAPED_UNICODE) : null,
                'occurred_at' => now(),
                'created_at' => now(),
            ]);
        } catch (\Throwable $e) {
            Log::warning('Failed to record simulation event', [
                'simulation_id' => $simulationId,
                'zone_id' => $zoneId,
                'service' => $service,
                'stage' => $stage,
                'status' => $status,
                'error' => $e->getMessage(),
            ]);
        }
    }

    private function resolveSimulation(int $simulationId): ?ZoneSimulation
    {
        $attempts = 0;
        while ($attempts < 5) {
            $simulation = ZoneSimulation::find($simulationId);
            if ($simulation) {
                return $simulation;
            }
            usleep(200000);
            $attempts++;
        }

        return null;
    }

    /**
     * Handle a job failure.
     */
    public function failed(\Throwable $exception): void
    {
        $simulationId = null;
        $cached = Cache::get("simulation:{$this->jobId}");
        if (is_array($cached) && isset($cached['simulation_id'])) {
            $simulationId = $cached['simulation_id'];
        }
        if ($simulationId) {
            $simulation = ZoneSimulation::find($simulationId);
            if ($simulation) {
                $this->recordSimulationEvent(
                    $simulationId,
                    $simulation->zone_id,
                    'laravel',
                    'job',
                    'failed',
                    'Симуляция завершилась ошибкой (retry exhausted)',
                    [
                        'job_id' => $this->jobId,
                        'error' => $exception->getMessage(),
                    ],
                    'error'
                );
            }
        }
        if ($simulationId) {
            ZoneSimulation::whereKey($simulationId)->update([
                'status' => 'failed',
                'error_message' => $exception->getMessage(),
            ]);
        }
        Cache::put("simulation:{$this->jobId}", [
            'status' => 'failed',
            'error' => $exception->getMessage(),
            'failed_at' => now()->toIso8601String(),
            'simulation_id' => $simulationId,
        ], 3600);

        Log::error('Simulation job failed permanently', [
            'job_id' => $this->jobId,
            'zone_id' => $this->zoneId,
            'error' => $exception->getMessage(),
        ]);
    }
}
