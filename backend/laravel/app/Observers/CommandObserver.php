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
        Log::info('[COMMAND_OBSERVER] STEP 1: created() called', [
            'command_id' => $command->cmd_id,
            'status' => $command->status ?? Command::STATUS_QUEUED,
            'zone_id' => $command->zone_id,
        ]);
        
        // Отправляем событие о создании команды
        try {
            Log::info('[COMMAND_OBSERVER] STEP 2: Dispatching CommandStatusUpdated event on create');
            event(new CommandStatusUpdated(
                commandId: $command->cmd_id,
                status: $command->status ?? Command::STATUS_QUEUED,
                message: 'Command created',
                zoneId: $command->zone_id
            ));
            Log::info('[COMMAND_OBSERVER] STEP 3: CommandStatusUpdated event dispatched on create', [
                'command_id' => $command->cmd_id,
            ]);
        } catch (\Exception $e) {
            Log::error('[COMMAND_OBSERVER] STEP 3: ERROR - Failed to broadcast CommandStatusUpdated on create', [
                'command_id' => $command->cmd_id,
                'error' => $e->getMessage(),
                'exception' => get_class($e),
            ]);
        }
    }

    /**
     * Handle the Command "updated" event.
     */
    public function updated(Command $command): void
    {
        Log::info('[COMMAND_OBSERVER] STEP 1: updated() called', [
            'command_id' => $command->cmd_id,
            'current_status' => $command->status,
        ]);
        
        // Проверяем, изменился ли статус
        $wasChanged = $command->wasChanged('status');
        Log::info('[COMMAND_OBSERVER] STEP 2: Checking if status changed', [
            'command_id' => $command->cmd_id,
            'wasChanged' => $wasChanged,
            'current_status' => $command->status,
            'original_status' => $command->getOriginal('status'),
            'dirty' => $command->getDirty(),
            'changes' => $command->getChanges(),
        ]);
        
        if ($wasChanged) {
            Log::info('[COMMAND_OBSERVER] STEP 3: Status changed, processing event', [
                'command_id' => $command->cmd_id,
            ]);
            $oldStatus = $command->getOriginal('status');
            $newStatus = $command->status;

            try {
                // Проверяем конечные статусы ошибок
                if (in_array($newStatus, [
                    Command::STATUS_ERROR,
                    Command::STATUS_INVALID,
                    Command::STATUS_BUSY,
                    Command::STATUS_TIMEOUT,
                    Command::STATUS_SEND_FAILED,
                ])) {
                    // Отправляем событие об ошибке
                    event(new CommandFailed(
                        commandId: $command->cmd_id,
                        message: 'Command failed',
                        error: $command->error_message ?? ($command->failed_at ? 'Command execution failed' : null),
                        status: $newStatus,
                        zoneId: $command->zone_id
                    ));
                } else {
                    // Отправляем событие об обновлении статуса
                    $message = match ($newStatus) {
                        Command::STATUS_QUEUED => 'Command queued',
                        Command::STATUS_SENT => 'Command sent',
                        Command::STATUS_ACK => 'Command acknowledged',
                        Command::STATUS_DONE => 'Command completed',
                        Command::STATUS_NO_EFFECT => 'Command completed with no effect',
                        default => 'Command status updated',
                    };

                    Log::info('[COMMAND_OBSERVER] STEP 4: Dispatching CommandStatusUpdated event', [
                        'command_id' => $command->cmd_id,
                        'status' => $newStatus,
                        'zone_id' => $command->zone_id,
                        'message' => $message,
                    ]);
                    event(new CommandStatusUpdated(
                        commandId: $command->cmd_id,
                        status: $newStatus,
                        message: $message,
                        zoneId: $command->zone_id
                    ));
                    Log::info('[COMMAND_OBSERVER] STEP 5: CommandStatusUpdated event dispatched successfully', [
                        'command_id' => $command->cmd_id,
                        'status' => $newStatus,
                    ]);
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
            if (in_array($newStatus, [
                Command::STATUS_ACK,
                Command::STATUS_DONE,
                Command::STATUS_NO_EFFECT,
                Command::STATUS_ERROR,
                Command::STATUS_INVALID,
                Command::STATUS_BUSY,
                Command::STATUS_TIMEOUT,
            ])) {
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
