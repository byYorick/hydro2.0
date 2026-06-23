<?php

namespace App\Console\Commands;

use App\Models\Command;
use App\Services\CommandTimeoutContextStore;
use Carbon\Carbon;
use Carbon\CarbonInterface;
use Illuminate\Console\Command as ConsoleCommand;
use Illuminate\Support\Facades\DB;
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
                $wasTimedOut = DB::transaction(function () use (
                    $command,
                    $timeoutMinutes,
                    $cutoff,
                    $nodeOfflineTimeoutSec,
                    $timeoutContextStore,
                ) {
                    $locked = Command::query()
                        ->where('id', $command->id)
                        ->whereIn('status', [Command::STATUS_SENT, Command::STATUS_ACK])
                        ->whereNotNull('sent_at')
                        ->where('sent_at', '<', $cutoff)
                        ->lockForUpdate()
                        ->first();

                    if (! $locked) {
                        Log::info('Skip timeout update due to concurrent status transition', [
                            'command_id' => $command->id,
                            'cmd_id' => $command->cmd_id,
                        ]);

                        return false;
                    }

                    $locked->loadMissing('node');
                    $node = $locked->node;
                    $nodeLastSeenAt = $node?->last_seen_at ? Carbon::parse($node->last_seen_at) : null;
                    $nodeLastSeenAgeSec = $nodeLastSeenAt instanceof CarbonInterface
                        ? (int) max(0, $nodeLastSeenAt->diffInSeconds(now()))
                        : null;
                    $nodeStatus = $node?->status ? strtolower((string) $node->status) : null;

                    $timeoutContextStore->put($locked->id, [
                        'command_id' => $locked->id,
                        'command' => $locked->cmd,
                        'source' => $locked->source,
                        'channel' => $locked->channel,
                        'node_uid' => $node?->uid,
                        'node_status' => $nodeStatus,
                        'node_last_seen_at' => $nodeLastSeenAt?->toIso8601String(),
                        'node_last_seen_age_sec' => $nodeLastSeenAgeSec,
                        'node_stale_online_candidate' => $nodeStatus === 'online'
                            && $nodeLastSeenAgeSec !== null
                            && $nodeLastSeenAgeSec >= $nodeOfflineTimeoutSec,
                        'timeout_minutes' => $timeoutMinutes,
                        'sent_at' => $locked->sent_at,
                    ]);

                    $locked->update([
                        'status' => Command::STATUS_TIMEOUT,
                        'failed_at' => now(),
                        'error_code' => 'command_timeout',
                        'result_code' => 1,
                    ]);

                    Log::info('Command timed out', [
                        'command_id' => $locked->id,
                        'cmd_id' => $locked->cmd_id,
                        'zone_id' => $locked->zone_id,
                        'timeout_minutes' => $timeoutMinutes,
                        'sent_at' => $locked->sent_at,
                    ]);

                    return true;
                });

                if ($wasTimedOut) {
                    $processed++;
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
}
