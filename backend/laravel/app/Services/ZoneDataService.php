<?php

namespace App\Services;

use App\Enums\GrowCycleStatus;
use App\Enums\ZoneStatus;
use App\Models\Alert;
use App\Models\Command;
use App\Models\DeviceNode;
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
            $latestTelemetryPerChannel = $this->getLatestTelemetryPerChannel($zone->id);

            $devices = DeviceNode::query()
                ->where('zone_id', $zone->id)
                ->orderBy('id')
                ->get()
                ->map(fn ($node) => [
                    'id' => $node->id,
                    'uid' => $node->uid,
                    'status' => $node->status,
                    'updated_at' => $node->updated_at?->toIso8601String(),
                ])
                ->values();

            $commandsRecent = Command::query()
                ->where('zone_id', $zone->id)
                ->orderBy('created_at', 'desc')
                ->orderBy('id', 'desc')
                ->limit(10)
                ->get()
                ->map(fn ($command) => [
                    'id' => $command->id,
                    'cmd_id' => $command->cmd_id,
                    'cmd' => $command->cmd,
                    'status' => $command->status,
                    'node_id' => $command->node_id,
                    'created_at' => $command->created_at?->toIso8601String(),
                ])
                ->values();

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
                            'event_id' => $event->id,
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
                'devices_online_state' => $devices,
                'zone' => $zoneInfo,
                'cycle' => $cycleInfo,
                'telemetry' => $telemetry,
                'latest_telemetry_per_channel' => $latestTelemetryPerChannel,
                'active_alerts' => $alerts,
                'commands_recent' => $commandsRecent,
                'recent_events' => $recentEvents,
                'nodes' => [], // Пока пустой массив, может быть заполнен позже
            ];
        });
    }

    /**
     * Получить события зоны
     */
    public function getEvents(Zone $zone, Request $request): array
    {
        $afterId = $request->integer('after_id');
        $limit = $request->integer('limit', 50);
        $limit = min(max($limit, 1), 200);

        $cycleOnly = $request->boolean('cycle_only', false);

        $query = DB::table('zone_events')
            ->where('zone_id', $zone->id);

        if ($cycleOnly) {
            $cycleEventTypes = [
                'CYCLE_CREATED',
                'CYCLE_STARTED',
                'CYCLE_PAUSED',
                'CYCLE_RESUMED',
                'CYCLE_HARVESTED',
                'CYCLE_ABORTED',
                'CYCLE_RECIPE_REBASED',
                'PHASE_TRANSITION',
                'RECIPE_PHASE_CHANGED',
                'ZONE_COMMAND',
            ];

            $query->where(function ($q) use ($cycleEventTypes) {
                $q->whereIn('type', $cycleEventTypes);
            });

            $detailsColumn = DB::getSchemaBuilder()->hasColumn('zone_events', 'payload_json')
                ? 'payload_json'
                : 'details';

            $query->orWhere(function ($q) use ($detailsColumn) {
                $q->whereIn('type', ['ALERT_CREATED', 'alert_created'])
                    ->whereRaw("{$detailsColumn}->>'severity' = 'CRITICAL'");
            });
        }

        $detailsColumn = DB::getSchemaBuilder()->hasColumn('zone_events', 'payload_json')
            ? 'payload_json'
            : 'details';

        if ($afterId > 0) {
            $query->where('id', '>', $afterId);
        }

        $events = $query->orderBy('id', 'asc')
            ->limit($limit)
            ->get([
                'id as event_id',
                'zone_id',
                'type',
                'server_ts',
                DB::raw("{$detailsColumn} as details"),
                'created_at',
            ])
            ->map(function ($event) {
                if (is_string($event->details)) {
                    $event->details = json_decode($event->details, true) ?? [];
                }
                $event->payload = $event->details;
                $event->payload_json = json_encode($event->details);
                return $event;
            })
            ->values();

        $lastEventId = $events->isNotEmpty()
            ? $events->last()->event_id
            : ($afterId > 0 ? $afterId : null);

        $hasMore = false;
        if ($lastEventId) {
            $hasMore = DB::table('zone_events')
                ->where('zone_id', $zone->id)
                ->where('id', '>', $lastEventId)
                ->exists();
        }

        return [
            'data' => $events->all(),
            'last_event_id' => $lastEventId,
            'has_more' => $hasMore,
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
        $limit = (int) $request->get('per_page', $request->get('limit', 10));
        $limit = min(max($limit, 1), 100);
        $severity = $request->get('severity');

        // Получаем ошибки из таблицы unassigned_node_errors для узлов зоны
        $query = UnassignedNodeError::where(function ($query) use ($zone) {
            $query->whereHas('node', function ($inner) use ($zone) {
                $inner->where('zone_id', $zone->id);
            })
            ->orWhere(function ($inner) {
                // Также включаем ошибки без node_id, но которые могут быть связаны с зоной
                // (в старой архитектуре могли быть ошибки без node_id)
                $inner->whereNull('node_id');
            });
        });

        if ($severity) {
            $query->where('severity', strtoupper($severity));
        }

        $errors = $query->orderBy('last_seen_at', 'desc')
            ->paginate($limit);

        $mapped = collect($errors->items())->map(function ($error) {
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
            'data' => $mapped->values()->all(),
            'meta' => [
                'current_page' => $errors->currentPage(),
                'last_page' => $errors->lastPage(),
                'per_page' => $errors->perPage(),
                'total' => $errors->total(),
            ],
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

    private function getLatestTelemetryPerChannel(int $zoneId): array
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
                'telemetry_last.last_ts',
                'telemetry_last.updated_at',
            ])
            ->orderBy('telemetry_last.updated_at', 'desc')
            ->get();

        $telemetry = [];
        foreach ($telemetryRaw as $item) {
            $channel = $item->channel ?: 'default';
            $nodeId = $item->node_id ?? 'unknown';

            if (!isset($telemetry[$channel])) {
                $telemetry[$channel] = [];
            }

            if (!isset($telemetry[$channel][$nodeId])) {
                $telemetry[$channel][$nodeId] = [];
            }

            $telemetry[$channel][$nodeId][] = [
                'metric_type' => $item->metric_type,
                'value' => (float) $item->value,
                'ts' => $item->last_ts?->toIso8601String(),
                'updated_at' => $item->updated_at?->toIso8601String(),
            ];
        }

        return $telemetry;
    }
}
