<?php

namespace App\Observers;

use App\Events\CommandFailed;
use App\Events\CommandStatusUpdated;
use App\Models\Command;
use App\Services\CommandTimeoutContextStore;
use App\Services\CommandTimeoutDiagnosticsBuilder;
use App\Services\PipelineMetricsService;
use App\Services\ZoneEventRecorder;
use Illuminate\Support\Facades\Log;

class CommandObserver
{
    public function __construct(
        private readonly ZoneEventRecorder $zoneEventRecorder,
        private readonly CommandTimeoutContextStore $timeoutContextStore,
        private readonly CommandTimeoutDiagnosticsBuilder $timeoutDiagnosticsBuilder,
    ) {}
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
                'exception' => get_class($e),
            ]);
        }
    }

    /**
     * Handle the Command "updated" event.
     */
    public function updated(Command $command): void
    {
        // Проверяем, изменился ли статус
        $wasChanged = $command->wasChanged('status');
        if ($wasChanged) {
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
                    $errorCode = $command->error_code;
                    $broadcastError = $command->error_message ?? $errorCode;

                    $failedEvent = new CommandFailed(
                        commandId: $command->cmd_id,
                        message: 'Command failed',
                        error: $broadcastError,
                        status: $newStatus,
                        zoneId: $command->zone_id,
                        errorCode: $errorCode
                    );
                    event($failedEvent);
                    $this->recordCommandStatusZoneEvent($command, $newStatus, $failedEvent);
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

                    $statusEvent = new CommandStatusUpdated(
                        commandId: $command->cmd_id,
                        status: $newStatus,
                        message: $message,
                        error: $command->error_message,
                        zoneId: $command->zone_id,
                        errorCode: $command->error_code
                    );
                    event($statusEvent);
                    $this->recordCommandStatusZoneEvent($command, $newStatus, $statusEvent);
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
                Command::STATUS_SEND_FAILED,
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

    private function recordCommandStatusZoneEvent(
        Command $command,
        string $status,
        CommandFailed|CommandStatusUpdated $event,
    ): void {
        if (! $command->zone_id) {
            return;
        }

        try {
            $extraPayload = [];
            if ($status === Command::STATUS_TIMEOUT) {
                $extraPayload = $this->timeoutContextStore->pull((int) $command->id);
                if ($extraPayload === []) {
                    $extraPayload = $this->timeoutDiagnosticsBuilder->fromCommand($command);
                }
            }

            $this->zoneEventRecorder->recordCommandStatus(
                zoneId: $command->zone_id,
                commandId: $command->cmd_id,
                status: $status,
                message: $event->message,
                error: $event->error,
                errorCode: $event->errorCode ?? $command->error_code,
                eventId: $event->eventId,
                serverTs: $event->serverTs,
                extraPayload: $extraPayload,
            );
        } catch (\Exception $e) {
            Log::error('Failed to record command_status zone event', [
                'command_id' => $command->cmd_id,
                'zone_id' => $command->zone_id,
                'status' => $status,
                'error' => $e->getMessage(),
            ]);
        }
    }
}
