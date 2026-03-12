<?php

namespace App\Console\Commands;

use App\Services\AutomationScheduler\ActiveTaskStore;
use App\Services\AutomationScheduler\SchedulerConstants;
use App\Services\AutomationScheduler\SchedulerRuntimeHelper;
use Illuminate\Console\Command;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Log;
use PDO;

/**
 * Long-running daemon that listens to PostgreSQL NOTIFY on the
 * scheduler_intent_terminal channel and updates laravel_scheduler_active_tasks
 * in near-realtime — without HTTP polling to the automation-engine.
 *
 * Run via supervisor or docker CMD (not via artisan schedule).
 *
 * Example:
 *   php artisan automation:intent-listener
 *   php artisan automation:intent-listener --timeout=3600
 */
class AutomationIntentListener extends Command
{
    protected $signature = 'automation:intent-listener
        {--timeout=0 : Max runtime in seconds (0 = run forever)}
        {--poll-interval=5000 : PDO pgsqlGetNotify timeout in ms per iteration}';

    protected $description = 'Listen to PostgreSQL NOTIFY for terminal intent status transitions and update active tasks';

    public function __construct(
        private readonly ActiveTaskStore $activeTaskStore,
    ) {
        parent::__construct();
    }

    public function handle(): int
    {
        $timeout = (int) $this->option('timeout');
        $pollInterval = max(100, (int) $this->option('poll-interval'));
        $startedAt = time();

        $this->info('automation:intent-listener starting — LISTEN scheduler_intent_terminal');
        Log::info('automation:intent-listener started', [
            'timeout' => $timeout,
            'poll_interval_ms' => $pollInterval,
        ]);

        try {
            $pdo = DB::connection()->getPdo();
        } catch (\Throwable $e) {
            $this->error('Failed to acquire PDO connection: '.$e->getMessage());
            Log::error('automation:intent-listener: failed to acquire PDO', [
                'error' => $e->getMessage(),
            ]);

            return Command::FAILURE;
        }

        try {
            $pdo->exec('LISTEN scheduler_intent_terminal');
        } catch (\Throwable $e) {
            $this->error('Failed to LISTEN on channel: '.$e->getMessage());
            Log::error('automation:intent-listener: LISTEN failed', [
                'error' => $e->getMessage(),
            ]);

            return Command::FAILURE;
        }

        $this->info('Listening… (press Ctrl+C to stop)');

        while (true) {
            if ($timeout > 0 && (time() - $startedAt) >= $timeout) {
                $this->info('Max timeout reached, exiting.');
                break;
            }

            try {
                $notification = $pdo->pgsqlGetNotify(PDO::FETCH_ASSOC, $pollInterval);
            } catch (\Throwable $e) {
                Log::warning('automation:intent-listener: pgsqlGetNotify error', [
                    'error' => $e->getMessage(),
                ]);
                // Brief pause before retry to avoid busy loop on persistent errors.
                usleep(500_000);

                continue;
            }

            if ($notification === false || $notification === null) {
                // No notification in this interval — normal, just continue.
                continue;
            }

            $payload = $notification['payload'] ?? '';
            if ($payload === '') {
                continue;
            }

            $this->processTerminalIntent($payload);
        }

        Log::info('automation:intent-listener stopped');

        return Command::SUCCESS;
    }

    private function processTerminalIntent(string $payload): void
    {
        $data = json_decode($payload, true);
        if (! is_array($data)) {
            Log::warning('automation:intent-listener: invalid JSON payload', [
                'payload' => $payload,
            ]);

            return;
        }

        $intentId = (int) ($data['intent_id'] ?? 0);
        $zoneId = (int) ($data['zone_id'] ?? 0);
        $intentStatus = strtolower(trim((string) ($data['status'] ?? '')));
        $errorCode = isset($data['error_code']) && $data['error_code'] !== null
            ? (string) $data['error_code']
            : null;

        if ($intentId <= 0 || $zoneId <= 0 || $intentStatus === '') {
            Log::debug('automation:intent-listener: skipping malformed notify', ['data' => $data]);

            return;
        }

        if (! in_array($intentStatus, SchedulerConstants::TERMINAL_STATUSES, true)) {
            // Shouldn't happen (trigger only fires on terminal), but guard anyway.
            return;
        }

        $terminalStatus = match ($intentStatus) {
            'completed' => 'completed',
            'cancelled' => 'cancelled',
            default => 'failed',
        };

        Log::debug('automation:intent-listener: processing terminal intent', [
            'intent_id' => $intentId,
            'zone_id' => $zoneId,
            'status' => $terminalStatus,
            'error_code' => $errorCode,
        ]);

        try {
            $task = $this->activeTaskStore->findByIntentId($intentId, $zoneId);
        } catch (\Throwable $e) {
            Log::warning('automation:intent-listener: findByIntentId failed', [
                'intent_id' => $intentId,
                'zone_id' => $zoneId,
                'error' => $e->getMessage(),
            ]);

            return;
        }

        if ($task === null) {
            // Task not tracked in laravel_scheduler_active_tasks — no action needed.
            Log::debug('automation:intent-listener: no active task for intent_id', [
                'intent_id' => $intentId,
                'zone_id' => $zoneId,
            ]);

            return;
        }

        $taskId = trim((string) $task->task_id);
        $persistedStatus = strtolower(trim((string) $task->status));
        if (in_array($persistedStatus, SchedulerConstants::TERMINAL_STATUSES, true)) {
            // Already terminal — nothing to update.
            return;
        }

        $now = SchedulerRuntimeHelper::nowUtc();
        try {
            $this->activeTaskStore->markTerminal(
                taskId: $taskId,
                status: $terminalStatus,
                terminalAt: $now,
                detailsPatch: [
                    'terminal_source' => 'intent_notify_listener',
                    'intent_id' => $intentId,
                    'error_code' => $errorCode,
                ],
                lastPolledAt: $now,
            );
        } catch (\Throwable $e) {
            Log::error('automation:intent-listener: markTerminal failed', [
                'task_id' => $taskId,
                'intent_id' => $intentId,
                'zone_id' => $zoneId,
                'error' => $e->getMessage(),
            ]);

            return;
        }

        Log::info('automation:intent-listener: marked task terminal via NOTIFY', [
            'task_id' => $taskId,
            'intent_id' => $intentId,
            'zone_id' => $zoneId,
            'status' => $terminalStatus,
        ]);
    }
}
