<?php

namespace App\Jobs;

use App\Services\AlertService;
use Illuminate\Bus\Queueable;
use Illuminate\Contracts\Queue\ShouldQueue;
use Illuminate\Foundation\Bus\Dispatchable;
use Illuminate\Queue\InteractsWithQueue;
use Illuminate\Queue\SerializesModels;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Log;

class ProcessAlert implements ShouldQueue
{
    use Dispatchable, InteractsWithQueue, Queueable, SerializesModels;

    /**
     * The number of times the job may be attempted.
     */
    public int $tries = 3;

    /**
     * The number of seconds to wait before retrying the job.
     */
    public int $backoff = 60; // Exponential backoff: 60s, 120s, 240s

    /**
     * @param array $alertData Данные алерта для создания
     */
    public function __construct(
        public array $alertData,
        public ?int $pendingAlertId = null
    ) {}

    /**
     * Execute the job.
     */
    public function handle(AlertService $alertService): void
    {
        try {
            // Создаем или обновляем алерт
            $result = $alertService->createOrUpdateActive($this->alertData);

            // Если был pending_alert_id - удаляем из pending_alerts
            if ($this->pendingAlertId) {
                DB::table('pending_alerts')
                    ->where('id', $this->pendingAlertId)
                    ->delete();

                Log::info('Pending alert processed and deleted', [
                    'pending_alert_id' => $this->pendingAlertId,
                    'alert_id' => $result['alert']->id ?? null,
                ]);
            }

        } catch (\Exception $e) {
            // Обновляем pending_alerts при ошибке
            if ($this->pendingAlertId) {
                $this->updatePendingAlertOnFailure($e);
            }

            Log::error('Failed to process alert', [
                'pending_alert_id' => $this->pendingAlertId,
                'error' => $e->getMessage(),
                'trace' => $e->getTraceAsString(),
            ]);

            throw $e; // Позволяем Laravel retry механизму обработать повтор
        }
    }

    /**
     * Обновить pending_alert при ошибке.
     */
    private function updatePendingAlertOnFailure(\Exception $e): void
    {
        try {
            $pending = DB::table('pending_alerts')
                ->where('id', $this->pendingAlertId)
                ->first();

            if (!$pending) {
                return;
            }

            $attempts = $pending->attempts + 1;
            $maxAttempts = $pending->max_attempts ?? 3;

            // Если превышен лимит попыток - перемещаем в DLQ
            if ($attempts >= $maxAttempts) {
                DB::table('pending_alerts')
                    ->where('id', $this->pendingAlertId)
                    ->update([
                        'status' => 'dlq',
                        'attempts' => $attempts,
                        'last_attempt_at' => now(),
                        'last_error' => $e->getMessage(),
                        'updated_at' => now(),
                    ]);

                Log::warning('Alert moved to DLQ after max attempts', [
                    'pending_alert_id' => $this->pendingAlertId,
                    'attempts' => $attempts,
                    'max_attempts' => $maxAttempts,
                ]);
            } else {
                // Обновляем счетчик попыток
                DB::table('pending_alerts')
                    ->where('id', $this->pendingAlertId)
                    ->update([
                        'attempts' => $attempts,
                        'last_attempt_at' => now(),
                        'last_error' => $e->getMessage(),
                        'status' => 'pending', // Остается pending для retry
                        'updated_at' => now(),
                    ]);
            }
        } catch (\Exception $updateException) {
            Log::error('Failed to update pending_alert on failure', [
                'pending_alert_id' => $this->pendingAlertId,
                'error' => $updateException->getMessage(),
            ]);
        }
    }

    /**
     * Calculate the number of seconds to wait before retrying the job.
     */
    public function backoff(): array
    {
        // Exponential backoff: 60s, 120s, 240s
        return [60, 120, 240];
    }
}

