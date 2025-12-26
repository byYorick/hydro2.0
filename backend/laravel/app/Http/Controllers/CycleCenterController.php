<?php

namespace App\Http\Controllers;

use App\Helpers\ZoneAccessHelper;
use App\Models\Alert;
use App\Models\TelemetryLast;
use App\Models\Zone;
use App\Services\GrowCyclePresenter;
use Illuminate\Http\Request;
use Inertia\Inertia;
use Inertia\Response;

class CycleCenterController extends Controller
{
    public function index(Request $request, GrowCyclePresenter $growCyclePresenter): Response
    {
        $user = $request->user();
        $accessibleZoneIds = ZoneAccessHelper::getAccessibleZoneIds($user);

        $zonesQuery = Zone::query()
            ->with([
                'greenhouse:id,name',
                'activeGrowCycle.currentPhase',
                'activeGrowCycle.recipeRevision.recipe:id,name',
                'activeGrowCycle.plant:id,name',
            ])
            ->withCount([
                'alerts as alerts_count' => function ($query) {
                    $query->where('status', 'ACTIVE');
                },
                'nodes as nodes_total',
                'nodes as nodes_online' => function ($query) {
                    $query->where('status', 'online');
                },
            ])
            ->orderBy('name');

        if (!$user?->isAdmin()) {
            $zonesQuery->whereIn('id', $accessibleZoneIds ?: [0]);
        }

        $zones = $zonesQuery->get();
        $zoneIds = $zones->pluck('id')->toArray();

        $telemetryByZone = [];
        if (!empty($zoneIds)) {
            $telemetryAll = TelemetryLast::query()
                ->whereIn('zone_id', $zoneIds)
                ->get(['zone_id', 'metric_type', 'value', 'updated_at']);

            foreach ($telemetryAll as $metric) {
                $zoneId = $metric->zone_id;
                $key = strtolower((string) ($metric->metric_type ?? ''));

                if (!isset($telemetryByZone[$zoneId])) {
                    $telemetryByZone[$zoneId] = [
                        'ph' => null,
                        'ec' => null,
                        'temperature' => null,
                        'humidity' => null,
                        'co2' => null,
                        'updated_at' => null,
                    ];
                }

                if ($key === 'ph') {
                    $telemetryByZone[$zoneId]['ph'] = (float) $metric->value;
                } elseif ($key === 'ec') {
                    $telemetryByZone[$zoneId]['ec'] = (float) $metric->value;
                } elseif (in_array($key, ['temp', 'temperature', 'air_temperature'], true)) {
                    $telemetryByZone[$zoneId]['temperature'] = (float) $metric->value;
                } elseif (in_array($key, ['humidity', 'rh'], true)) {
                    $telemetryByZone[$zoneId]['humidity'] = (float) $metric->value;
                } elseif ($key === 'co2') {
                    $telemetryByZone[$zoneId]['co2'] = (float) $metric->value;
                }

                if ($metric->updated_at) {
                    $lastUpdated = $telemetryByZone[$zoneId]['updated_at'];
                    if (!$lastUpdated || $metric->updated_at->gt($lastUpdated)) {
                        $telemetryByZone[$zoneId]['updated_at'] = $metric->updated_at->toIso8601String();
                    }
                }
            }
        }

        $alertsByZone = [];
        if (!empty($zoneIds)) {
            $alerts = Alert::query()
                ->whereIn('zone_id', $zoneIds)
                ->where('status', 'ACTIVE')
                ->orderBy('created_at', 'desc')
                ->get()
                ->groupBy('zone_id');

            foreach ($alerts as $zoneId => $zoneAlerts) {
                $alertsByZone[$zoneId] = $zoneAlerts->take(2)->values()->map(function ($alert) {
                    return [
                        'id' => $alert->id,
                        'type' => $alert->type,
                        'details' => $alert->details,
                        'created_at' => $alert->created_at?->toIso8601String(),
                    ];
                })->toArray();
            }
        }

        $summary = [
            'zones_total' => $zones->count(),
            'cycles_running' => 0,
            'cycles_paused' => 0,
            'cycles_planned' => 0,
            'cycles_none' => 0,
            'alerts_active' => $zones->sum('alerts_count'),
            'devices_online' => $zones->sum('nodes_online'),
            'devices_total' => $zones->sum('nodes_total'),
        ];

        foreach ($zones as $zone) {
            $cycle = $zone->activeGrowCycle;
            if (!$cycle) {
                $summary['cycles_none']++;
                continue;
            }

            switch ($cycle->status->value) {
                case 'RUNNING':
                    $summary['cycles_running']++;
                    break;
                case 'PAUSED':
                    $summary['cycles_paused']++;
                    break;
                case 'PLANNED':
                    $summary['cycles_planned']++;
                    break;
                default:
                    break;
            }
        }

        $zonesData = $zones->map(function (Zone $zone) use ($telemetryByZone, $alertsByZone, $growCyclePresenter) {
            $cycle = $zone->activeGrowCycle;
            $cycleDto = $cycle ? $growCyclePresenter->buildCycleDto($cycle)['cycle'] ?? null : null;

            $recipe = null;
            // Используем новую модель: activeGrowCycle -> recipeRevision -> recipe
            if ($cycle?->recipeRevision?->recipe) {
                $recipe = [
                    'id' => $cycle->recipeRevision->recipe->id,
                    'name' => $cycle->recipeRevision->recipe->name,
                ];
            } elseif ($cycle?->recipe) {
                // Fallback на старую структуру (если есть прямая связь)
                $recipe = [
                    'id' => $cycle->recipe->id,
                    'name' => $cycle->recipe->name,
                ];
            }

            return [
                'id' => $zone->id,
                'name' => $zone->name,
                'status' => $zone->status,
                'greenhouse' => $zone->greenhouse ? [
                    'id' => $zone->greenhouse->id,
                    'name' => $zone->greenhouse->name,
                ] : null,
                'telemetry' => $telemetryByZone[$zone->id] ?? [
                    'ph' => null,
                    'ec' => null,
                    'temperature' => null,
                    'humidity' => null,
                    'co2' => null,
                    'updated_at' => null,
                ],
                'alerts_count' => (int) ($zone->alerts_count ?? 0),
                'alerts_preview' => $alertsByZone[$zone->id] ?? [],
                'devices' => [
                    'total' => (int) ($zone->nodes_total ?? 0),
                    'online' => (int) ($zone->nodes_online ?? 0),
                ],
                'recipe' => $recipe,
                'plant' => $cycle?->plant ? [
                    'id' => $cycle->plant->id,
                    'name' => $cycle->plant->name,
                ] : null,
                'cycle' => $cycleDto,
            ];
        })->values();

        $greenhouses = $zones->map(function (Zone $zone) {
            if (!$zone->greenhouse) {
                return null;
            }

            return [
                'id' => $zone->greenhouse->id,
                'name' => $zone->greenhouse->name,
            ];
        })->filter()->unique('id')->values();

        return Inertia::render('Cycles/Center', [
            'auth' => ['user' => ['role' => $user?->role ?? 'viewer']],
            'summary' => $summary,
            'zones' => $zonesData,
            'greenhouses' => $greenhouses,
        ]);
    }
}
