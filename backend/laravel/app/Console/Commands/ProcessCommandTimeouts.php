<?php

namespace App\Console\Commands;

use App\Events\CommandStatusUpdated;
use Illuminate\Console\Command;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Log;

class ProcessCommandTimeouts extends Command
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
        $this->info("Processing command timeouts (timeout: {$timeoutMinutes} minutes)");

        // Ищем команды в статусах SENT/ACK, которые старше timeout
        $timeoutCommands = DB::table('commands')
            ->whereIn('status', ['SENT', 'ACK'])
            ->whereNotNull('sent_at')
            ->where('sent_at', '<', $cutoff)
            ->get();

        if ($timeoutCommands->isEmpty()) {
            $this->info('No commands found to timeout');
            return Command::SUCCESS;
        }

        $this->info("Found {$timeoutCommands->count()} command(s) to timeout");

        $processed = 0;
        foreach ($timeoutCommands as $command) {
            try {
                $wasTimedOut = DB::transaction(function () use ($command, $timeoutMinutes, $cutoff) {
                    // Обновляем статус на TIMEOUT
                    $updated = DB::table('commands')
                        ->where('id', $command->id)
                        ->whereIn('status', ['SENT', 'ACK'])
                        ->whereNotNull('sent_at')
                        ->where('sent_at', '<', $cutoff)
                        ->update([
                            'status' => 'TIMEOUT',
                            'failed_at' => now(),
                            'error_code' => 'TIMEOUT',
                            'result_code' => 1,
                            'updated_at' => now(),
                        ]);

                    if ($updated === 0) {
                        Log::info('Skip timeout update due to concurrent status transition', [
                            'command_id' => $command->id,
                            'cmd_id' => $command->cmd_id ?? null,
                        ]);
                        return false;
                    }

                    // Создаем событие в zone_events
                    if ($command->zone_id) {
                        DB::table('zone_events')->insert([
                            'zone_id' => $command->zone_id,
                            'type' => 'COMMAND_TIMEOUT',
                            'payload_json' => json_encode([
                                'command_id' => $command->id,
                                'cmd_id' => $command->cmd_id ?? null,
                                'timeout_minutes' => $timeoutMinutes,
                                'sent_at' => $command->sent_at,
                            ]),
                            'created_at' => now(),
                        ]);
                    }

                    // Отправляем WebSocket уведомление
                    // commandId должен быть cmd_id (строка), а не id (integer)
                    event(new CommandStatusUpdated(
                        commandId: $command->cmd_id ?? (string)$command->id,
                        status: 'TIMEOUT',
                        message: "Command timed out after {$timeoutMinutes} minutes",
                        error: null,
                        zoneId: $command->zone_id
                    ));

                    Log::info('Command timed out', [
                        'command_id' => $command->id,
                        'cmd_id' => $command->cmd_id ?? null,
                        'zone_id' => $command->zone_id,
                        'timeout_minutes' => $timeoutMinutes,
                        'sent_at' => $command->sent_at,
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
        return Command::SUCCESS;
    }
}
