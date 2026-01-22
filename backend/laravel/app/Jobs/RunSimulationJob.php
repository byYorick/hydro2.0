<?php

namespace App\Jobs;

use App\Services\DigitalTwinClient;
use App\Jobs\CompleteSimulationJob;
use App\Models\ZoneSimulation;
use Illuminate\Bus\Queueable;
use Illuminate\Contracts\Queue\ShouldQueue;
use Illuminate\Foundation\Bus\Dispatchable;
use Illuminate\Queue\InteractsWithQueue;
use Illuminate\Queue\SerializesModels;
use Illuminate\Support\Facades\Log;
use Illuminate\Support\Facades\Cache;

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
    public function handle(DigitalTwinClient $client): void
    {
        $simulation = null;
        try {
            $durationHours = $this->params['duration_hours'] ?? 72;
            $stepMinutes = $this->params['step_minutes'] ?? 10;
            $scenario = is_array($this->params['scenario'] ?? null)
                ? $this->params['scenario']
                : [];
            $simDurationMinutes = $this->params['sim_duration_minutes'] ?? null;
            $isLiveSimulation = is_numeric($simDurationMinutes) && (int) $simDurationMinutes > 0;

            $nowIso = now()->toIso8601String();
            $simulationMeta = [
                'real_started_at' => $nowIso,
                'sim_started_at' => $nowIso,
            ];
            if ($isLiveSimulation) {
                $timeScale = ($durationHours * 60) / (int) $simDurationMinutes;
                $simulationMeta['real_duration_minutes'] = (int) $simDurationMinutes;
                $simulationMeta['time_scale'] = $timeScale;
            }

            $existingMeta = [];
            if (isset($scenario['simulation']) && is_array($scenario['simulation'])) {
                $existingMeta = $scenario['simulation'];
            }
            $scenario['simulation'] = array_merge($existingMeta, $simulationMeta);
            $scenarioPayload = $scenario;
            unset($scenarioPayload['simulation']);

            $simulation = ZoneSimulation::create([
                'zone_id' => $this->zoneId,
                'scenario' => $scenario,
                'duration_hours' => $durationHours,
                'step_minutes' => $stepMinutes,
                'status' => 'running',
            ]);

            // Устанавливаем статус "processing"
            Cache::put("simulation:{$this->jobId}", [
                'status' => 'processing',
                'started_at' => now()->toIso8601String(),
                'simulation_id' => $simulation->id,
                'sim_duration_minutes' => $isLiveSimulation ? (int) $simDurationMinutes : null,
            ], 3600); // Храним 1 час

            if ($isLiveSimulation) {
                CompleteSimulationJob::dispatch($simulation->id, $this->jobId)
                    ->delay(now()->addMinutes((int) $simDurationMinutes));
                Log::info('Simulation job scheduled completion', [
                    'job_id' => $this->jobId,
                    'zone_id' => $this->zoneId,
                    'simulation_id' => $simulation->id,
                    'real_duration_minutes' => (int) $simDurationMinutes,
                ]);
                return;
            }

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
            if (!app()->environment('testing')) {
                throw $e; // Пробрасываем для retry механизма
            }
        }
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
