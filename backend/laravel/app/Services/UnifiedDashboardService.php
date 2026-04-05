<?php

namespace App\Services;

use App\Helpers\ZoneAccessHelper;
use App\Models\Alert;
use App\Models\User;
use App\Models\Zone;
use Illuminate\Database\Eloquent\Collection;
use Illuminate\Support\Facades\Cache;

class UnifiedDashboardService
{
    public function __construct(
        private GrowCyclePresenter $growCyclePresenter,
        private ZoneFrontendTelemetryService $zoneFrontendTelemetry,
        private ZoneIrrigationModalContextService $irrigationModalContext,
    ) {}

    /**
     * @return array{summary: array, zonesData: array<int, array>, greenhouses: array<int, array>, latestAlerts: Collection<int, Alert>}
     */
    public function getData(?User $user): array
    {
        $userId = $user?->id ?? 0;
        $cacheKey = "unified_dashboard_{$userId}";

        return Cache::remember($cacheKey, 30, function () use ($user) {
            return $this->buildUncachedData($user);
        });
    }

    /**
     * @return array{summary: array, zonesData: array<int, array>, greenhouses: array<int, array>, latestAlerts: Collection<int, Alert>}
     */
    private function buildUncachedData(?User $user): array
    {
        $accessibleZoneIds = ZoneAccessHelper::getAccessibleZoneIds($user);

        $zones = Zone::query()
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
            ->when(! $user?->isAdmin(), fn ($q) => $q->whereIn('id', $accessibleZoneIds ?: [0]))
            ->orderByRaw("CASE status WHEN 'ALARM' THEN 1 WHEN 'WARNING' THEN 2 WHEN 'RUNNING' THEN 3 WHEN 'PAUSED' THEN 4 ELSE 5 END")
            ->orderBy('name')
            ->get();

        $zoneIds = $zones->pluck('id')->toArray();

        $telemetryByZone = $this->zoneFrontendTelemetry->getZoneSnapshots($zoneIds, true);
        $alertsByZone = $this->getAlertsByZone($zoneIds);
        $latestAlerts = $this->getLatestAlerts($user, $accessibleZoneIds);
        $summary = $this->buildSummary($zones);
        $zonesData = $this->formatZones($zones, $telemetryByZone, $alertsByZone);
        $greenhouses = $this->getGreenhouses($zones);

        return [
            'summary' => $summary,
            'zonesData' => $zonesData,
            'greenhouses' => $greenhouses,
            'latestAlerts' => $latestAlerts,
        ];
    }

    /**
     * @param  array<int>  $zoneIds
     * @return array<int, array<int, array{id: int, type: string, details: string, created_at: string|null}>>
     */
    private function getAlertsByZone(array $zoneIds): array
    {
        if (empty($zoneIds)) {
            return [];
        }

        $alerts = Alert::query()
            ->whereIn('zone_id', $zoneIds)
            ->where('status', 'ACTIVE')
            ->orderBy('created_at', 'desc')
            ->get()
            ->groupBy('zone_id');

        $alertsByZone = [];
        foreach ($alerts as $zoneId => $zoneAlerts) {
            $alertsByZone[$zoneId] = $zoneAlerts->take(2)->values()->map(function ($alert) {
                return [
                    'id' => $alert->id,
                    'type' => $alert->type,
                    'details' => is_array($alert->details)
                        ? (string) json_encode($alert->details)
                        : (string) $alert->details,
                    'created_at' => $alert->created_at?->toIso8601String(),
                ];
            })->toArray();
        }

        return $alertsByZone;
    }

    /**
     * @return Collection<int, Alert>
     */
    private function getLatestAlerts(?User $user, array $accessibleZoneIds)
    {
        $latestAlertsQuery = Alert::query()
            ->select(['id', 'type', 'status', 'details', 'zone_id', 'created_at'])
            ->with('zone:id,name')
            ->where('status', 'ACTIVE');

        if (! $user?->isAdmin()) {
            $latestAlertsQuery->whereIn('zone_id', $accessibleZoneIds ?: [0]);
        }

        return $latestAlertsQuery
            ->latest('id')
            ->limit(10)
            ->get();
    }

    private function buildSummary(Collection $zones): array
    {
        $greenhouseIds = $zones->pluck('greenhouse_id')->filter()->unique()->values();

        $summary = [
            'zones_total' => $zones->count(),
            'zones_running' => $zones->where('status', 'RUNNING')->count(),
            'zones_warning' => $zones->where('status', 'WARNING')->count(),
            'zones_alarm' => $zones->where('status', 'ALARM')->count(),
            'cycles_running' => 0,
            'cycles_paused' => 0,
            'cycles_planned' => 0,
            'cycles_none' => 0,
            'alerts_active' => (int) $zones->sum('alerts_count'),
            'devices_online' => (int) $zones->sum('nodes_online'),
            'devices_total' => (int) $zones->sum('nodes_total'),
            'greenhouses_count' => $greenhouseIds->count(),
        ];

        foreach ($zones as $zone) {
            $cycle = $zone->activeGrowCycle;
            if (! $cycle) {
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

        return $summary;
    }

    /**
     * @param  array<int, array>  $telemetryByZone
     * @param  array<int, array>  $alertsByZone
     * @return array<int, array<string, mixed>>
     */
    private function formatZones(Collection $zones, array $telemetryByZone, array $alertsByZone): array
    {
        return $zones->map(function (Zone $zone) use ($telemetryByZone, $alertsByZone) {
            $cycle = $zone->activeGrowCycle;
            $cycleDto = $cycle ? ($this->growCyclePresenter->buildCycleDto($cycle)['cycle'] ?? null) : null;

            $recipe = null;
            if ($cycle?->recipeRevision?->recipe) {
                $recipe = [
                    'id' => $cycle->recipeRevision->recipe->id,
                    'name' => $cycle->recipeRevision->recipe->name,
                ];
            } elseif ($cycle?->recipe) {
                $recipe = [
                    'id' => $cycle->recipe->id,
                    'name' => $cycle->recipe->name,
                ];
            }

            $crop = $cycle?->plant?->name ?? $recipe['name'] ?? null;
            $ctx = $this->irrigationModalContext->buildForZone($zone);

            return [
                'id' => $zone->id,
                'name' => $zone->name,
                'status' => $zone->status,
                'greenhouse' => $zone->greenhouse ? [
                    'id' => $zone->greenhouse->id,
                    'name' => $zone->greenhouse->name,
                ] : null,
                'telemetry' => $this->normalizeTelemetrySnapshot($telemetryByZone[$zone->id] ?? []),
                'targets' => $ctx['targets'],
                'current_phase_targets' => $ctx['current_phase_targets'],
                'irrigation_correction_summary' => $ctx['irrigation_correction_summary'],
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
                'crop' => $crop,
            ];
        })->values()->toArray();
    }

    /**
     * Нормализует telemetry_last под контракт фронтенда.
     *
     * @param  array<string, mixed>  $telemetry
     * @return array{ph: float|null, ec: float|null, temperature: float|null, humidity: float|null, co2: float|null, updated_at: string|null}
     */
    private function normalizeTelemetrySnapshot(array $telemetry): array
    {
        $ph = isset($telemetry['ph']) && is_numeric($telemetry['ph']) ? (float) $telemetry['ph'] : null;
        $ecRaw = isset($telemetry['ec']) && is_numeric($telemetry['ec']) ? (float) $telemetry['ec'] : null;
        $temperature = isset($telemetry['temperature']) && is_numeric($telemetry['temperature']) ? (float) $telemetry['temperature'] : null;
        $humidity = isset($telemetry['humidity']) && is_numeric($telemetry['humidity']) ? (float) $telemetry['humidity'] : null;
        $co2 = isset($telemetry['co2']) && is_numeric($telemetry['co2']) ? (float) $telemetry['co2'] : null;

        // Некоторые узлы отдают EC в µS/см. Для UI приводим к мСм/см, если значение явно «большое».
        $ec = $ecRaw;
        if ($ecRaw !== null && $ecRaw > 20.0) {
            $ec = $ecRaw / 1000.0;
        }

        $updatedAt = null;
        if (isset($telemetry['updated_at']) && is_string($telemetry['updated_at']) && $telemetry['updated_at'] !== '') {
            $updatedAt = $telemetry['updated_at'];
        } elseif (isset($telemetry['last_updated']) && is_string($telemetry['last_updated']) && $telemetry['last_updated'] !== '') {
            $updatedAt = $telemetry['last_updated'];
        }

        return [
            'ph' => $ph,
            'ec' => $ec,
            'temperature' => $temperature,
            'humidity' => $humidity,
            'co2' => $co2,
            'updated_at' => $updatedAt,
        ];
    }

    /**
     * @return array<int, array{id: int, name: string}>
     */
    private function getGreenhouses(Collection $zones): array
    {
        return $zones->map(function (Zone $zone) {
            if (! $zone->greenhouse) {
                return null;
            }

            return [
                'id' => $zone->greenhouse->id,
                'name' => $zone->greenhouse->name,
            ];
        })->filter()->unique('id')->values()->toArray();
    }
}
