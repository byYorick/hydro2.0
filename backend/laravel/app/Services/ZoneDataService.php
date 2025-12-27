<?php

namespace App\Services;

use App\Enums\GrowCycleStatus;
use App\Enums\ZoneStatus;
use App\Models\Alert;
use App\Models\GrowCycle;
use App\Models\TelemetryLast;
use App\Models\UnassignedNodeError;
use App\Models\Zone;
use App\Models\ZoneEvent;
use Illuminate\Http\Request;
use Illuminate\Support\Collection;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Log;

class ZoneDataService
{
    /**
     * Получить snapshot зоны
     */
    public function getSnapshot(Zone $zone, Request $request): array
    {
        return DB::transaction(function () use ($zone, $request) {
            $now = now();
            $serverTs = $now->timestamp * 1000; // миллисекунды
            $snapshotId = \Illuminate\Support\Str::uuid()->toString();

            // Получаем максимальный last_event_id для зоны
            $lastEventId = ZoneEvent::where('zone_id', $zone->id)->max('id') ?? 0;

            // Получаем телеметрию
            $telemetry = $this->getZoneTelemetryGrouped($zone->id);

            // Получаем активные алерты
            $alerts = Alert::where('zone_id', $zone->id)
                ->where('status', 'ACTIVE')
                ->orderBy('created_at', 'desc')
                ->get()
                ->map(function ($alert) {
                    return [
                        'id' => $alert->id,
                        'type' => $alert->type,
                        'details' => $alert->details,
                        'created_at' => $alert->created_at?->toIso8601String(),
                    ];
                });

            // Получаем информацию о цикле
            $cycleInfo = null;
            if ($zone->activeGrowCycle) {
                $cycle = $zone->activeGrowCycle;
                $cycleInfo = [
                    'id' => $cycle->id,
                    'status' => $cycle->status instanceof \BackedEnum ? $cycle->status->value : $cycle->status,
                    'current_phase_index' => $cycle->current_phase_index,
                    'current_phase_name' => $cycle->currentPhase?->name,
                    'recipe_name' => $cycle->recipeRevision?->recipe?->name,
                    'plant_name' => $cycle->plant?->name,
                    'started_at' => $cycle->started_at?->toIso8601String(),
                    'estimated_harvest_at' => $cycle->estimated_harvest_at?->toIso8601String(),
                ];
            }

            // Получаем информацию о зоне
            $zoneInfo = [
                'id' => $zone->id,
                'uid' => $zone->uid,
                'name' => $zone->name,
                'status' => $zone->status,
                'greenhouse_id' => $zone->greenhouse_id,
                'greenhouse_name' => $zone->greenhouse?->name,
                'preset_id' => $zone->preset_id,
                'preset_name' => $zone->preset?->name,
            ];

            // Получаем последние события (опционально)
            $recentEvents = [];
            if ($request->boolean('include_events', false)) {
                $recentEvents = ZoneEvent::where('zone_id', $zone->id)
                    ->orderBy('created_at', 'desc')
                    ->limit(10)
                    ->get()
                    ->map(function ($event) {
                        return [
                            'id' => $event->id,
                            'type' => $event->type,
                            'data' => $event->data,
                            'created_at' => $event->created_at?->toIso8601String(),
                        ];
                    });
            }

            return [
                'snapshot_id' => $snapshotId,
                'server_ts' => $serverTs,
                'zone_id' => $zone->id,
                'last_event_id' => $lastEventId,
                'zone' => $zoneInfo,
                'cycle' => $cycleInfo,
                'telemetry' => $telemetry,
                'active_alerts' => $alerts,
                'recent_commands' => $recentEvents,
                'nodes' => [], // Пока пустой массив, может быть заполнен позже
            ];
        });
    }

    /**
     * Получить события зоны
     */
    public function getEvents(Zone $zone, Request $request): array
    {
        $query = ZoneEvent::where('zone_id', $zone->id);

        // Фильтрация по типу события
        if ($request->has('type')) {
            $query->where('type', $request->string('type'));
        }

        // Фильтрация по времени
        if ($request->has('since')) {
            $query->where('created_at', '>', $request->date('since'));
        }

        if ($request->has('until')) {
            $query->where('created_at', '<=', $request->date('until'));
        }

        // Пагинация
        $perPage = $request->integer('per_page', 50);
        $page = $request->integer('page', 1);

        $events = $query->orderBy('created_at', 'desc')
            ->paginate($perPage, ['*'], 'page', $page);

        return [
            'events' => $events->items(),
            'pagination' => [
                'current_page' => $events->currentPage(),
                'last_page' => $events->lastPage(),
                'per_page' => $events->perPage(),
                'total' => $events->total(),
            ],
        ];
    }

    /**
     * Получить циклы зоны
     */
    public function getCycles(Zone $zone, Request $request): array
    {
        $query = GrowCycle::where('zone_id', $zone->id)
            ->with([
                'recipeRevision.recipe:id,name',
                'plant:id,name',
                'currentPhase:id,name',
            ]);

        // Фильтрация по статусу
        if ($request->has('status')) {
            $status = $request->enum('status', GrowCycleStatus::class);
            $query->where('status', $status);
        }

        // Пагинация
        $perPage = $request->integer('per_page', 20);
        $cycles = $query->orderBy('created_at', 'desc')
            ->paginate($perPage);

        return [
            'cycles' => $cycles->items(),
            'pagination' => [
                'current_page' => $cycles->currentPage(),
                'last_page' => $cycles->lastPage(),
                'per_page' => $cycles->perPage(),
                'total' => $cycles->total(),
            ],
        ];
    }

    /**
     * Получить неназначенные ошибки зоны
     */
    public function getUnassignedErrors(Zone $zone, Request $request): array
    {
        $limit = $request->get('limit', 10);

        // Получаем ошибки из таблицы unassigned_node_errors для узлов зоны
        $errors = UnassignedNodeError::whereHas('node', function ($query) use ($zone) {
            $query->where('zone_id', $zone->id);
        })
        ->orWhere(function ($query) use ($zone) {
            // Также включаем ошибки без node_id, но которые могут быть связаны с зоной
            // (в старой архитектуре могли быть ошибки без node_id)
            $query->whereNull('node_id');
        })
        ->orderBy('last_seen_at', 'desc')
        ->limit($limit)
        ->get()
        ->map(function ($error) {
            return [
                'id' => $error->id,
                'hardware_id' => $error->hardware_id,
                'error_message' => $error->error_message,
                'error_code' => $error->error_code,
                'severity' => $error->severity ?? 'ERROR', // Устанавливаем дефолтное значение
                'topic' => $error->topic,
                'last_payload' => $error->last_payload,
                'count' => $error->count,
                'first_seen_at' => $error->first_seen_at?->toIso8601String(),
                'last_seen_at' => $error->last_seen_at?->toIso8601String(),
                'node_id' => $error->node_id,
                'created_at' => $error->created_at?->toIso8601String(),
                'updated_at' => $error->updated_at?->toIso8601String(),
            ];
        });

        return [
            'errors' => $errors,
            'total' => $errors->count(),
        ];
    }

    /**
     * Получить сгруппированную телеметрию для зоны
     */
    private function getZoneTelemetryGrouped(int $zoneId): array
    {
        $telemetryRaw = TelemetryLast::query()
            ->join('sensors', 'telemetry_last.sensor_id', '=', 'sensors.id')
            ->where('sensors.zone_id', $zoneId)
            ->whereNotNull('sensors.zone_id')
            ->select([
                'sensors.node_id',
                'sensors.label as channel',
                'sensors.type as metric_type',
                'telemetry_last.last_value as value',
                'telemetry_last.updated_at'
            ])
            ->orderBy('telemetry_last.updated_at', 'desc')
            ->get();

        // Группируем по node_id, затем по channel
        $telemetry = [];
        foreach ($telemetryRaw as $item) {
            $nodeId = $item->node_id ?? 'unknown';
            $channel = $item->channel ?: 'default';

            if (!isset($telemetry[$nodeId])) {
                $telemetry[$nodeId] = [];
            }

            $telemetry[$nodeId][$channel] = [
                'metric_type' => $item->metric_type,
                'value' => (float) $item->value,
                'updated_at' => $item->updated_at?->toIso8601String(),
            ];
        }

        return $telemetry;
    }
}
