<?php

namespace App\Observers;

use App\Events\EventCreated;
use App\Models\ZoneEvent;
use App\Services\ZoneEventMessageFormatter;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Log;

class ZoneEventObserver
{
    /**
     * Handle the ZoneEvent "created" event.
     */
    public function created(ZoneEvent $zoneEvent): void
    {
        $dispatch = function () use ($zoneEvent): void {
            try {
                $payload = is_array($zoneEvent->payload_json) ? $zoneEvent->payload_json : [];
                if ($payload === [] && is_array($zoneEvent->details)) {
                    $payload = $zoneEvent->details;
                }
                $formatter = app(ZoneEventMessageFormatter::class);
                $type = $zoneEvent->type ?? 'INFO';
                $message = $formatter->format($type, $payload);

                $wsEventId = isset($payload['ws_event_id']) && is_numeric($payload['ws_event_id'])
                    ? (int) $payload['ws_event_id']
                    : null;
                $serverTs = is_numeric($zoneEvent->server_ts ?? null)
                    ? (int) $zoneEvent->server_ts
                    : null;

                event(new EventCreated(
                    id: $zoneEvent->id,
                    kind: $type,
                    message: $message,
                    zoneId: $zoneEvent->zone_id,
                    occurredAt: $zoneEvent->created_at?->toIso8601String() ?? now()->toIso8601String(),
                    payload: $payload !== [] ? $payload : null,
                    eventId: $wsEventId,
                    serverTs: $serverTs,
                ));
            } catch (\Exception $e) {
                Log::error('Failed to broadcast EventCreated', [
                    'zone_event_id' => $zoneEvent->id,
                    'error' => $e->getMessage(),
                ]);
            }
        };

        if (DB::transactionLevel() > 0 && ! app()->runningUnitTests()) {
            DB::afterCommit($dispatch);
        } else {
            $dispatch();
        }
    }
}
