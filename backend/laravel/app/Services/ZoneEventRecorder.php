<?php

namespace App\Services;

use App\Traits\RecordsZoneEvent;

/**
 * Запись событий в zone_events вне broadcast lifecycle.
 * Использует Eloquent → ZoneEventObserver эмитит EventCreated для live-ленты.
 */
class ZoneEventRecorder
{
    use RecordsZoneEvent;

    /**
     * @param  array<string, mixed>|null  $payload
     * @return int|null ID созданной записи
     */
    public function record(
        int $zoneId,
        string $type,
        ?string $entityType = null,
        int|string|null $entityId = null,
        ?array $payload = null,
        ?int $eventId = null,
        ?int $serverTs = null,
    ): ?int {
        return $this->recordZoneEvent(
            zoneId: $zoneId,
            type: $type,
            entityType: $entityType,
            entityId: $entityId,
            payload: $payload,
            eventId: $eventId,
            serverTs: $serverTs,
        );
    }

    /**
     * @param  array<string, mixed>  $extraPayload
     * @return int|null ID созданной записи
     */
    public function recordCommandStatus(
        int $zoneId,
        int|string $commandId,
        string $status,
        ?string $message = null,
        ?string $error = null,
        ?string $errorCode = null,
        ?int $eventId = null,
        ?int $serverTs = null,
        array $extraPayload = [],
    ): ?int {
        return $this->recordZoneEvent(
            zoneId: $zoneId,
            type: 'command_status',
            entityType: 'command',
            entityId: $commandId,
            payload: array_merge([
                'status' => $status,
                'message' => $message,
                'error' => $error,
                'error_code' => $errorCode,
                'cmd_id' => (string) $commandId,
            ], $extraPayload),
            eventId: $eventId,
            serverTs: $serverTs,
        );
    }
}
