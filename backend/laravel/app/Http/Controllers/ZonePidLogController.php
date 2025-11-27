<?php

namespace App\Http\Controllers;

use App\Models\Zone;
use App\Models\ZoneEvent;
use Illuminate\Http\JsonResponse;
use Illuminate\Http\Request;

class ZonePidLogController extends Controller
{
    /**
     * Получить логи PID для зоны
     */
    public function index(Request $request, Zone $zone): JsonResponse
    {
        $validated = $request->validate([
            'type' => ['nullable', 'string', 'in:ph,ec'],
            'limit' => ['nullable', 'integer', 'min:1', 'max:200'],
            'offset' => ['nullable', 'integer', 'min:0'],
        ]);

        $type = $validated['type'] ?? null;
        $limit = $validated['limit'] ?? 50;
        $offset = $validated['offset'] ?? 0;

        $query = ZoneEvent::where('zone_id', $zone->id)
            ->whereIn('type', ['PID_OUTPUT', 'PID_CONFIG_UPDATED']);

        // Фильтр по типу (для PID_OUTPUT)
        if ($type) {
            $query->where(function ($q) use ($type) {
                $q->where('type', 'PID_CONFIG_UPDATED')
                    ->whereJsonContains('details->type', $type)
                    ->orWhere(function ($q2) use ($type) {
                        $q2->where('type', 'PID_OUTPUT')
                            ->whereJsonContains('details->type', $type);
                    });
            });
        }

        $events = $query->orderBy('created_at', 'desc')
            ->offset($offset)
            ->limit($limit)
            ->get();

        // Преобразуем события в формат логов
        $logs = $events->map(function ($event) {
            $details = $event->details ?? [];

            if ($event->type === 'PID_OUTPUT') {
                return [
                    'id' => $event->id,
                    'type' => $details['type'] ?? null,
                    'zone_state' => $details['zone_state'] ?? null,
                    'output' => $details['output'] ?? null,
                    'error' => $details['error'] ?? null,
                    'dt_seconds' => $details['dt_seconds'] ?? null,
                    'current' => $details['current'] ?? null,
                    'target' => $details['target'] ?? null,
                    'safety_skip_reason' => $details['safety_skip_reason'] ?? null,
                    'created_at' => $event->created_at->toIso8601String(),
                ];
            } else { // PID_CONFIG_UPDATED
                return [
                    'id' => $event->id,
                    'type' => 'config_updated',
                    'pid_type' => $details['type'] ?? null,
                    'old_config' => $details['old_config'] ?? null,
                    'new_config' => $details['new_config'] ?? null,
                    'updated_by' => $details['updated_by'] ?? null,
                    'created_at' => $event->created_at->toIso8601String(),
                ];
            }
        });

        return response()->json([
            'status' => 'ok',
            'data' => $logs,
            'meta' => [
                'total' => $query->count(),
                'limit' => $limit,
                'offset' => $offset,
            ],
        ]);
    }
}
