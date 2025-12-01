<?php

namespace App\Jobs;

use App\Services\DigitalTwinClient;
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
        try {
            // Устанавливаем статус "processing"
            Cache::put("simulation:{$this->jobId}", [
                'status' => 'processing',
                'started_at' => now()->toIso8601String(),
            ], 3600); // Храним 1 час

            // Выполняем симуляцию
            $result = $client->simulateZone($this->zoneId, $this->params);

            // Сохраняем результат
            Cache::put("simulation:{$this->jobId}", [
                'status' => 'completed',
                'result' => $result,
                'completed_at' => now()->toIso8601String(),
            ], 3600);

            Log::info('Simulation job completed', [
                'job_id' => $this->jobId,
                'zone_id' => $this->zoneId,
            ]);
        } catch (\Exception $e) {
            // Сохраняем ошибку
            Cache::put("simulation:{$this->jobId}", [
                'status' => 'failed',
                'error' => $e->getMessage(),
                'failed_at' => now()->toIso8601String(),
            ], 3600);

            Log::error('Simulation job failed', [
                'job_id' => $this->jobId,
                'zone_id' => $this->zoneId,
                'error' => $e->getMessage(),
                'exception' => get_class($e),
            ]);

            throw $e; // Пробрасываем для retry механизма
        }
    }

    /**
     * Handle a job failure.
     */
    public function failed(\Throwable $exception): void
    {
        Cache::put("simulation:{$this->jobId}", [
            'status' => 'failed',
            'error' => $exception->getMessage(),
            'failed_at' => now()->toIso8601String(),
        ], 3600);

        Log::error('Simulation job failed permanently', [
            'job_id' => $this->jobId,
            'zone_id' => $this->zoneId,
            'error' => $exception->getMessage(),
        ]);
    }
}

