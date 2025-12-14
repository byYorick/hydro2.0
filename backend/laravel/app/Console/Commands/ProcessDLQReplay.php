<?php

namespace App\Console\Commands;

use App\Jobs\ProcessAlert;
use Illuminate\Console\Command;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Log;

class ProcessDLQReplay extends Command
{
    /**
     * The name and signature of the console command.
     *
     * @var string
     */
    protected $signature = 'alerts:dlq-replay 
                            {--older-than-hours=24 : Replay alerts older than N hours}
                            {--limit=100 : Maximum number of alerts to replay}';

    /**
     * The console command description.
     *
     * @var string
     */
    protected $description = 'Automatically replay old alerts from DLQ (default: older than 24 hours)';

    /**
     * Execute the console command.
     */
    public function handle(): int
    {
        $olderThanHours = (int) $this->option('older-than-hours');
        $limit = (int) $this->option('limit');

        $this->info("Replaying DLQ alerts older than {$olderThanHours} hours (limit: {$limit})");

        // Ищем записи в DLQ старше указанного времени
        $dlqAlerts = DB::table('pending_alerts')
            ->where('status', 'dlq')
            ->where('created_at', '<', now()->subHours($olderThanHours))
            ->limit($limit)
            ->get();

        if ($dlqAlerts->isEmpty()) {
            $this->info('No DLQ alerts found to replay');
            return Command::SUCCESS;
        }

        $this->info("Found {$dlqAlerts->count()} alert(s) to replay");

        $replayed = 0;
        foreach ($dlqAlerts as $pendingAlert) {
            try {
                // Обновляем статус обратно на pending и сбрасываем счетчик попыток
                DB::table('pending_alerts')
                    ->where('id', $pendingAlert->id)
                    ->update([
                        'status' => 'pending',
                        'attempts' => 0,
                        'last_error' => null,
                        'last_attempt_at' => null,
                        'updated_at' => now(),
                    ]);

                // Создаем Job для обработки алерта
                $alertData = [
                    'zone_id' => $pendingAlert->zone_id,
                    'source' => $pendingAlert->source ?? 'biz',
                    'code' => $pendingAlert->code,
                    'type' => $pendingAlert->type,
                    'details' => $pendingAlert->details ? json_decode($pendingAlert->details, true) : null,
                ];

                ProcessAlert::dispatch($alertData, $pendingAlert->id);

                $replayed++;
            } catch (\Exception $e) {
                Log::error('Failed to replay DLQ alert', [
                    'pending_alert_id' => $pendingAlert->id,
                    'error' => $e->getMessage(),
                ]);
                $this->error("Failed to replay alert {$pendingAlert->id}: {$e->getMessage()}");
            }
        }

        $this->info("Replayed {$replayed} alert(s)");
        return Command::SUCCESS;
    }
}

