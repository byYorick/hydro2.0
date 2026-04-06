<?php

namespace App\Observers;

use App\Events\EventCreated;
use App\Models\ZoneEvent;
use App\Services\ZoneEventMessageFormatter;
use Illuminate\Support\Facades\Log;

class ZoneEventObserver
{
    /**
     * Handle the ZoneEvent "created" event.
     */
    public function created(ZoneEvent $zoneEvent): void
    {
        try {
            $payload = is_array($zoneEvent->payload_json) ? $zoneEvent->payload_json : [];
            if ($payload === [] && is_array($zoneEvent->details)) {
                $payload = $zoneEvent->details;
            }
            $formatter = app(ZoneEventMessageFormatter::class);
            $type = $zoneEvent->type ?? 'INFO';
            $message = $formatter->format($type, $payload);

            event(new EventCreated(
                id: $zoneEvent->id,
                kind: $type,
                message: $message,
                zoneId: $zoneEvent->zone_id,
                occurredAt: $zoneEvent->created_at?->toIso8601String() ?? now()->toIso8601String(),
                payload: $payload !== [] ? $payload : null
            ));
        } catch (\Exception $e) {
            Log::error('Failed to broadcast EventCreated', [
                'zone_event_id' => $zoneEvent->id,
                'error' => $e->getMessage(),
            ]);
        }
    }
}
