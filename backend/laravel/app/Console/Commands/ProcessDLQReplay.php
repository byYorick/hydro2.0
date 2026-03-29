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
        $dlqAlerts = DB::table('pending_alerts_dlq')
            ->where('created_at', '<', now()->subHours($olderThanHours))
            ->limit($limit)
            ->get();

        if ($dlqAlerts->isEmpty()) {
            $this->info('No DLQ alerts found to replay');
            return Command::SUCCESS;
        }

        $this->info("Found {$dlqAlerts->count()} alert(s) to replay");

        $replayed = 0;
        foreach ($dlqAlerts as $dlqAlert) {
            try {
                $newPendingId = DB::transaction(function () use ($dlqAlert) {
                    $pendingId = DB::table('pending_alerts')->insertGetId([
                        'zone_id' => $dlqAlert->zone_id,
                        'source' => $dlqAlert->source ?? 'biz',
                        'code' => $dlqAlert->code,
                        'type' => $dlqAlert->type,
                        'status' => 'pending',
                        'attempts' => 0,
                        'max_attempts' => $dlqAlert->max_attempts ?? 3,
                        'details' => $dlqAlert->details,
                        'last_error' => null,
                        'next_retry_at' => now(),
                        'moved_to_dlq_at' => null,
                        'created_at' => now(),
                        'updated_at' => now(),
                    ]);

                    DB::table('pending_alerts_dlq')
                        ->where('id', $dlqAlert->id)
                        ->delete();

                    return $pendingId;
                });

                $alertData = [
                    'zone_id' => $dlqAlert->zone_id,
                    'source' => $dlqAlert->source ?? 'biz',
                    'code' => $dlqAlert->code,
                    'type' => $dlqAlert->type,
                    'details' => $dlqAlert->details ? json_decode($dlqAlert->details, true) : null,
                ];

                ProcessAlert::dispatch($alertData, $newPendingId);

                $replayed++;
            } catch (\Exception $e) {
                Log::error('Failed to replay DLQ alert', [
                    'pending_alert_id' => $dlqAlert->id,
                    'error' => $e->getMessage(),
                ]);
                $this->error("Failed to replay alert {$dlqAlert->id}: {$e->getMessage()}");
            }
        }

        $this->info("Replayed {$replayed} alert(s)");
        return Command::SUCCESS;
    }
}
