<?php

namespace App\Console\Commands;

use App\Models\Command;
use App\Services\CommandTimeoutContextStore;
use Carbon\Carbon;
use Carbon\CarbonInterface;
use Illuminate\Console\Command as ConsoleCommand;
use Illuminate\Support\Facades\Log;

class ProcessCommandTimeouts extends ConsoleCommand
{
    /**
     * The name and signature of the console command.
     *
     * @var string
     */
    protected $signature = 'commands:process-timeouts';

    /**
     * The console command description.
     *
     * @var string
     */
    protected $description = 'Process commands that have timed out (status SENT/ACK older than configured timeout)';

    /**
     * Execute the console command.
     *
     * Durable TIMEOUT transition uses a conditional UPDATE (no SELECT-then-UPDATE race).
     * Side-effects (timeout context + Eloquent observer / zone_events) run after a successful
     * UPDATE; failures there are logged and do not undo TIMEOUT or under-count processed rows.
     * If the process dies after UPDATE but before side-effects, a later run will not re-TIMEOUT
     * the same row (status already terminal) — events may be missing once, never duplicated.
     */
    public function handle(): int
    {
        $timeoutMinutes = config('commands.timeout_minutes', 5);
        $cutoff = now()->subMinutes($timeoutMinutes);
        $nodeOfflineTimeoutSec = max(1, (int) env('NODE_OFFLINE_TIMEOUT_SEC', 120));
        $timeoutContextStore = app(CommandTimeoutContextStore::class);
        $this->info("Processing command timeouts (timeout: {$timeoutMinutes} minutes)");

        $timeoutCommands = Command::query()
            ->with('node')
            ->whereIn('status', [Command::STATUS_SENT, Command::STATUS_ACK])
            ->whereNotNull('sent_at')
            ->where('sent_at', '<', $cutoff)
            ->get();

        if ($timeoutCommands->isEmpty()) {
            $this->info('No commands found to timeout');

            return ConsoleCommand::SUCCESS;
        }

        $this->info("Found {$timeoutCommands->count()} command(s) to timeout");

        $processed = 0;
        foreach ($timeoutCommands as $command) {
            try {
                $priorStatus = $command->status;
                $failedAt = now();
                $updated = Command::query()
                    ->where('id', $command->id)
                    ->whereIn('status', [Command::STATUS_SENT, Command::STATUS_ACK])
                    ->whereNotNull('sent_at')
                    ->where('sent_at', '<', $cutoff)
                    ->update([
                        'status' => Command::STATUS_TIMEOUT,
                        'failed_at' => $failedAt,
                        'error_code' => 'command_timeout',
                        'result_code' => 1,
                    ]);

                if ($updated === 0) {
                    Log::info('Skip timeout update due to concurrent status transition', [
                        'command_id' => $command->id,
                        'cmd_id' => $command->cmd_id,
                    ]);

                    continue;
                }

                // Durable transition succeeded — count even if side-effects fail below.
                $processed++;

                try {
                    $this->emitTimeoutSideEffects(
                        $command,
                        $priorStatus,
                        $failedAt,
                        $timeoutMinutes,
                        $nodeOfflineTimeoutSec,
                        $timeoutContextStore,
                    );
                } catch (\Throwable $e) {
                    Log::error('Failed to emit command timeout side-effects after status update', [
                        'command_id' => $command->id,
                        'cmd_id' => $command->cmd_id,
                        'error' => $e->getMessage(),
                        'trace' => $e->getTraceAsString(),
                    ]);
                    $this->error(
                        "Timeout side-effects failed for command {$command->id} "
                        ."(status already TIMEOUT): {$e->getMessage()}"
                    );
                }
            } catch (\Exception $e) {
                Log::error('Failed to process command timeout', [
                    'command_id' => $command->id,
                    'error' => $e->getMessage(),
                    'trace' => $e->getTraceAsString(),
                ]);
                $this->error("Failed to timeout command {$command->id}: {$e->getMessage()}");
            }
        }

        $this->info("Processed {$processed} command(s)");

        return ConsoleCommand::SUCCESS;
    }

    /**
     * Reload the row after conditional UPDATE and dispatch Eloquent observers.
     * Query-builder UPDATE skips model events; we synthesize wasChanged('status')
     * so CommandObserver records command_status exactly once.
     */
    private function emitTimeoutSideEffects(
        Command $command,
        mixed $priorStatus,
        CarbonInterface $failedAt,
        int $timeoutMinutes,
        int $nodeOfflineTimeoutSec,
        CommandTimeoutContextStore $timeoutContextStore,
    ): void {
        $node = $command->node;
        $nodeLastSeenAt = $node?->last_seen_at ? Carbon::parse($node->last_seen_at) : null;
        $nodeLastSeenAgeSec = $nodeLastSeenAt instanceof CarbonInterface
            ? (int) max(0, $nodeLastSeenAt->diffInSeconds(now()))
            : null;
        $nodeStatus = $node?->status ? strtolower((string) $node->status) : null;

        $timeoutContextStore->put($command->id, [
            'command_id' => $command->id,
            'command' => $command->cmd,
            'source' => $command->source,
            'channel' => $command->channel,
            'node_uid' => $node?->uid,
            'node_status' => $nodeStatus,
            'node_last_seen_at' => $nodeLastSeenAt?->toIso8601String(),
            'node_last_seen_age_sec' => $nodeLastSeenAgeSec,
            'node_stale_online_candidate' => $nodeStatus === 'online'
                && $nodeLastSeenAgeSec !== null
                && $nodeLastSeenAgeSec >= $nodeOfflineTimeoutSec,
            'timeout_minutes' => $timeoutMinutes,
            'sent_at' => $command->sent_at,
        ]);

        $command->refresh();

        // Restore pre-UPDATE status as original so wasChanged('status') is true for observers.
        $command->setRawAttributes(
            array_merge($command->getAttributes(), ['status' => $priorStatus]),
            true,
        );
        $command->forceFill([
            'status' => Command::STATUS_TIMEOUT,
            'failed_at' => $command->failed_at ?? $failedAt,
            'error_code' => $command->error_code ?? 'command_timeout',
            'result_code' => $command->result_code ?? 1,
        ]);
        $command->syncChanges();

        Command::getEventDispatcher()?->dispatch(
            'eloquent.updated: '.Command::class,
            $command,
        );

        Log::info('Command timed out', [
            'command_id' => $command->id,
            'cmd_id' => $command->cmd_id,
            'zone_id' => $command->zone_id,
            'timeout_minutes' => $timeoutMinutes,
            'sent_at' => $command->sent_at,
        ]);
    }
}
