<?php

namespace App\Observers;

use App\Models\ZoneEvent;
use App\Events\EventCreated;
use Illuminate\Support\Facades\Log;

class ZoneEventObserver
{
    /**
     * Handle the ZoneEvent "created" event.
     */
    public function created(ZoneEvent $zoneEvent): void
    {
        // Отправляем событие о создании события зоны
        try {
            // Формируем сообщение из type и details
            $message = $zoneEvent->type ?? 'Zone event occurred';
            if ($zoneEvent->details && is_array($zoneEvent->details)) {
                $detailsStr = json_encode($zoneEvent->details);
                if (strlen($detailsStr) < 200) {
                    $message .= ': ' . $detailsStr;
                }
            }
            
            event(new EventCreated(
                id: $zoneEvent->id,
                kind: $zoneEvent->type ?? 'INFO',
                message: $message,
                zoneId: $zoneEvent->zone_id,
                occurredAt: $zoneEvent->created_at?->toIso8601String() ?? now()->toIso8601String()
            ));
        } catch (\Exception $e) {
            Log::error('Failed to broadcast EventCreated', [
                'zone_event_id' => $zoneEvent->id,
                'error' => $e->getMessage(),
            ]);
        }
    }
}

