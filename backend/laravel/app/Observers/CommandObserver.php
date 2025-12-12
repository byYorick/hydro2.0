<?php

namespace App\Observers;

use App\Events\CommandFailed;
use App\Events\CommandStatusUpdated;
use App\Models\Command;
use App\Services\PipelineMetricsService;
use Illuminate\Support\Facades\Log;

class CommandObserver
{
    /**
     * Handle the Command "created" event.
     */
    public function created(Command $command): void
    {
        // Отправляем событие о создании команды
        try {
            event(new CommandStatusUpdated(
                commandId: $command->cmd_id,
                status: $command->status ?? Command::STATUS_QUEUED,
                message: 'Command created',
                zoneId: $command->zone_id
            ));
        } catch (\Exception $e) {
            Log::error('Failed to broadcast CommandStatusUpdated on create', [
                'command_id' => $command->cmd_id,
                'error' => $e->getMessage(),
            ]);
        }
    }

    /**
     * Handle the Command "updated" event.
     */
    public function updated(Command $command): void
    {
        // Проверяем, изменился ли статус
        if ($command->wasChanged('status')) {
            $oldStatus = $command->getOriginal('status');
            $newStatus = $command->status;

            try {
                // Проверяем конечные статусы ошибок
                if (in_array($newStatus, [Command::STATUS_FAILED, Command::STATUS_TIMEOUT, Command::STATUS_SEND_FAILED])) {
                    // Отправляем событие об ошибке
                    event(new CommandFailed(
                        commandId: $command->cmd_id,
                        message: 'Command failed',
                        error: $command->error_message ?? ($command->failed_at ? 'Command execution failed' : null),
                        zoneId: $command->zone_id
                    ));
                } else {
                    // Отправляем событие об обновлении статуса
                    $message = match ($newStatus) {
                        Command::STATUS_QUEUED => 'Command queued',
                        Command::STATUS_SENT => 'Command sent',
                        Command::STATUS_ACCEPTED => 'Command accepted',
                        Command::STATUS_DONE => 'Command completed',
                        default => 'Command status updated',
                    };

                    event(new CommandStatusUpdated(
                        commandId: $command->cmd_id,
                        status: $newStatus,
                        message: $message,
                        zoneId: $command->zone_id
                    ));
                }
            } catch (\Exception $e) {
                Log::error('Failed to broadcast command event on update', [
                    'command_id' => $command->cmd_id,
                    'old_status' => $oldStatus,
                    'new_status' => $newStatus,
                    'error' => $e->getMessage(),
                ]);
            }
            
            // Записываем метрики latency для команды
            if (in_array($newStatus, [Command::STATUS_ACCEPTED, Command::STATUS_DONE, Command::STATUS_FAILED, Command::STATUS_TIMEOUT])) {
                try {
                    $metricsService = app(PipelineMetricsService::class);
                    $metricsService->recordCommandLatency($command);
                } catch (\Exception $e) {
                    // Не логируем ошибки метрик
                }
            }
        }
    }
}
