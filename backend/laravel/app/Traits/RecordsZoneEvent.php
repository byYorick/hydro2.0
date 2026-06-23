<?php

namespace App\Traits;

use App\Models\ZoneEvent;
use Illuminate\Support\Facades\Log;

/**
 * Trait для записи событий в zone_events (Zone Event Ledger).
 *
 * Запись через Eloquent ZoneEvent → ZoneEventObserver эмитит EventCreated (afterCommit).
 */
trait RecordsZoneEvent
{
    /**
     * Записывает событие в zone_events.
     *
     * @param  int|null  $zoneId  ID зоны (если null, событие не записывается)
     * @param  string  $type  Тип события (telemetry_updated, command_status, alert_created, etc.)
     * @param  string|null  $entityType  Тип сущности (command, alert, telemetry, device)
     * @param  int|string|null  $entityId  ID сущности
     * @param  array|null  $payload  Минимально необходимые данные для события
     * @param  int|null  $eventId  ID события из EventSequenceService
     * @param  int|null  $serverTs  Временная метка сервера в миллисекундах
     * @return int|null ID созданной записи или null если не записано
     */
    protected function recordZoneEvent(
        ?int $zoneId,
        string $type,
        ?string $entityType = null,
        int|string|null $entityId = null,
        ?array $payload = null,
        ?int $eventId = null,
        ?int $serverTs = null
    ): ?int {
        // Если zone_id не указан, не записываем событие
        if (! $zoneId) {
            return null;
        }

        try {
            // Записываем событие сразу
            // Broadcast события обычно отправляются после commit транзакции через очередь
            // Но мы записываем в zone_events сразу, чтобы гарантировать порядок
            return $this->insertZoneEvent($zoneId, $type, $entityType, $entityId, $payload, $eventId, $serverTs);
        } catch (\Exception $e) {
            Log::error('Failed to record zone event', [
                'zone_id' => $zoneId,
                'type' => $type,
                'error' => $e->getMessage(),
                'trace' => $e->getTraceAsString(),
            ]);

            return null;
        }
    }

    /**
     * Вставляет событие в zone_events.
     *
     * Использует event_id из EventSequenceService для синхронизации с WS событиями.
     * id в таблице автоинкрементный, но для запросов по after_id используется id (который монотонно возрастает).
     */
    private function insertZoneEvent(
        int $zoneId,
        string $type,
        ?string $entityType,
        int|string|null $entityId,
        ?array $payload,
        ?int $eventId,
        ?int $serverTs
    ): ?int {
        // Если event_id не передан, генерируем новый (но лучше использовать из события)
        if (! $eventId || ! $serverTs) {
            $sequence = \App\Services\EventSequenceService::generateEventId();
            $eventId = $eventId ?? $sequence['event_id'];
            $serverTs = $serverTs ?? $sequence['server_ts'];
        }

        // Вставляем событие в zone_events
        // id автоинкрементный, но мы также сохраняем event_id из WS события в payload для связи
        $payloadWithEventId = $payload ?? [];
        $payloadWithEventId['ws_event_id'] = $eventId;

        $zoneEvent = ZoneEvent::create([
            'zone_id' => $zoneId,
            'type' => $type,
            'entity_type' => $entityType,
            'entity_id' => $entityId ? (string) $entityId : null,
            'payload_json' => $payloadWithEventId,
            'server_ts' => $serverTs,
            'created_at' => now(),
        ]);

        return $zoneEvent->id;
    }

    /**
     * Метод по умолчанию для broadcast-событий с RecordsZoneEvent.
     * Для command_status и большинства audit trail используйте ZoneEventRecorder/ZoneEvent::create.
     */
    public function broadcasted(): void
    {
        // По умолчанию ничего не делаем
        // Каждое событие должно переопределить этот метод и вызвать recordZoneEvent
    }
}
