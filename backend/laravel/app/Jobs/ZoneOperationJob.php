<?php

namespace App\Jobs;

use App\Models\Zone;
use App\Services\ZoneService;
use Illuminate\Bus\Queueable;
use Illuminate\Contracts\Queue\ShouldQueue;
use Illuminate\Foundation\Bus\Dispatchable;
use Illuminate\Queue\InteractsWithQueue;
use Illuminate\Queue\SerializesModels;
use Illuminate\Support\Facades\Log;

class ZoneOperationJob implements ShouldQueue
{
    use Dispatchable, InteractsWithQueue, Queueable, SerializesModels;

    public int $timeout = 400; // 6.5 минут (больше чем max_duration_sec 600)

    /**
     * Create a new job instance.
     */
    public function __construct(
        public int $zoneId,
        public string $operation, // 'fill', 'drain', 'calibrateFlow'
        public array $data,
        public string $jobId // Для отслеживания статуса
    ) {
        //
    }

    /**
     * Execute the job.
     */
    public function handle(ZoneService $zoneService): void
    {
        try {
            $zone = Zone::findOrFail($this->zoneId);
            
            // Устанавливаем статус "processing"
            \Illuminate\Support\Facades\Cache::put("zone_operation:{$this->jobId}", [
                'status' => 'processing',
                'operation' => $this->operation,
                'zone_id' => $this->zoneId,
                'started_at' => now()->toIso8601String(),
            ], 3600); // Храним 1 час

            // Выполняем операцию
            $result = match($this->operation) {
                'fill' => $zoneService->fill($zone, $this->data),
                'drain' => $zoneService->drain($zone, $this->data),
                'calibrateFlow' => $zoneService->calibrateFlow($zone, $this->data),
                default => throw new \InvalidArgumentException("Unknown operation: {$this->operation}"),
            };

            // Сохраняем результат
            \Illuminate\Support\Facades\Cache::put("zone_operation:{$this->jobId}", [
                'status' => 'completed',
                'operation' => $this->operation,
                'zone_id' => $this->zoneId,
                'result' => $result,
                'completed_at' => now()->toIso8601String(),
            ], 3600);

            Log::info('Zone operation job completed', [
                'job_id' => $this->jobId,
                'zone_id' => $this->zoneId,
                'operation' => $this->operation,
            ]);
        } catch (\Exception $e) {
            // Сохраняем ошибку
            \Illuminate\Support\Facades\Cache::put("zone_operation:{$this->jobId}", [
                'status' => 'failed',
                'operation' => $this->operation,
                'zone_id' => $this->zoneId,
                'error' => $e->getMessage(),
                'failed_at' => now()->toIso8601String(),
            ], 3600);

            Log::error('Zone operation job failed', [
                'job_id' => $this->jobId,
                'zone_id' => $this->zoneId,
                'operation' => $this->operation,
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
        \Illuminate\Support\Facades\Cache::put("zone_operation:{$this->jobId}", [
            'status' => 'failed',
            'operation' => $this->operation,
            'zone_id' => $this->zoneId,
            'error' => $exception->getMessage(),
            'failed_at' => now()->toIso8601String(),
        ], 3600);

        Log::error('Zone operation job failed permanently', [
            'job_id' => $this->jobId,
            'zone_id' => $this->zoneId,
            'operation' => $this->operation,
            'error' => $exception->getMessage(),
        ]);
    }
}

