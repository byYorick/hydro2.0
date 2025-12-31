<?php

/*
|--------------------------------------------------------------------------
| Greenhouses, Zones & Nodes Web Routes
|--------------------------------------------------------------------------
|
| Веб-маршруты для управления теплицами, зонами и узлами.
| Доступны пользователям с ролями viewer/operator/admin/agronomist.
|
*/

use Illuminate\Support\Facades\Route;
use Illuminate\Support\Facades\DB;
use Inertia\Inertia;
use App\Models\Alert;
use App\Models\DeviceNode;
use App\Models\Greenhouse;
use App\Models\TelemetryLast;
use App\Models\Zone;

Route::middleware(['web', 'auth', 'role:viewer,operator,admin,agronomist'])->group(function () {
    /**
     * Dashboard - главная страница
     *
     * Inertia Props:
     * - auth: { user: { role: 'viewer'|'operator'|'admin' } }
     * - dashboard: {
     *     greenhousesCount: int,
     *     zonesCount: int,
     *     devicesCount: int,
     *     alertsCount: int,
     *     zonesByStatus: { 'RUNNING': int, 'PAUSED': int, 'WARNING': int, 'ALARM': int },
     *     nodesByStatus: { 'online': int, 'offline': int },
     *     problematicZones: Array<{ id, name, status, description, greenhouse_id, greenhouse, alerts_count }>,
     *     greenhouses: Array<{ id, uid, name, type, zones_count, zones_running }>,
     *     zones: Array<{ id, name, status, greenhouse: { id, name } }>,
     *     latestAlerts: Array<{ id, type, status, details, zone_id, created_at, zone }>
     *   }
     *
     * Кеширование: 30 секунд
     */
    Route::get('/', function () {
        // Обрабатываем ошибки БД для предотвращения 500 и бесконечных перезагрузок
        // Используем кеш для статических данных (TTL 30 секунд)
        // Пользователь уже проверен middleware 'auth'
        $user = auth()->user();

        // Получаем доступные зоны для пользователя для tenant-изоляции
        $accessibleZoneIds = \App\Helpers\ZoneAccessHelper::getAccessibleZoneIds($user);
        $accessibleNodeIds = \App\Helpers\ZoneAccessHelper::getAccessibleNodeIds($user);

        $cacheKey = 'dashboard_data_'.auth()->id();
        try {
            $dashboard = \Illuminate\Support\Facades\Cache::remember($cacheKey, 30, function () use ($user, $accessibleZoneIds, $accessibleNodeIds) {
                // Обрабатываем ошибки БД внутри кеша
                try {
                    // Фильтруем статистику по доступным зонам/нодам (кроме админов)
                    if ($user->isAdmin()) {
                        $stats = DB::select("
                            SELECT 
                                (SELECT COUNT(*) FROM greenhouses) as greenhouses_count,
                                (SELECT COUNT(*) FROM zones) as zones_count,
                                (SELECT COUNT(*) FROM nodes) as devices_count,
                                (SELECT COUNT(*) FROM alerts WHERE status = 'ACTIVE') as alerts_count
                        ")[0];
                    } else {
                        // Используем параметризованные запросы для безопасности
                        $zoneIds = $accessibleZoneIds ?: [0];
                        $nodeIds = $accessibleNodeIds ?: [0];
                        $zonePlaceholders = implode(',', array_fill(0, count($zoneIds), '?'));
                        $nodePlaceholders = implode(',', array_fill(0, count($nodeIds), '?'));
                        $stats = DB::select("
                            SELECT 
                                (SELECT COUNT(DISTINCT greenhouse_id) FROM zones WHERE id IN ($zonePlaceholders)) as greenhouses_count,
                                (SELECT COUNT(*) FROM zones WHERE id IN ($zonePlaceholders)) as zones_count,
                                (SELECT COUNT(*) FROM nodes WHERE id IN ($nodePlaceholders)) as devices_count,
                                (SELECT COUNT(*) FROM alerts WHERE status = 'ACTIVE' AND zone_id IN ($zonePlaceholders)) as alerts_count
                        ", array_merge($zoneIds, $zoneIds, $nodeIds, $zoneIds))[0];
                    }
                } catch (\Illuminate\Database\QueryException $e) {
                    // Если таблицы не существуют, возвращаем нулевые значения
                    \Log::error('Dashboard: Database error in stats query', [
                        'error' => $e->getMessage(),
                        'user_id' => auth()->id(),
                    ]);
                    $stats = (object) [
                        'greenhouses_count' => 0,
                        'zones_count' => 0,
                        'devices_count' => 0,
                        'alerts_count' => 0,
                    ];
                }

                // Обрабатываем ошибки БД для всех запросов
                // Если таблицы не существуют или БД недоступна, возвращаем пустые данные
                try {
                    $zonesByStatusQuery = Zone::query();
                    if (! $user->isAdmin()) {
                        $zonesByStatusQuery->whereIn('id', $accessibleZoneIds ?: [0]);
                    }
                    $zonesByStatus = $zonesByStatusQuery
                        ->selectRaw('status, COUNT(*) as count')
                        ->groupBy('status')
                        ->pluck('count', 'status')
                        ->toArray();
                } catch (\Exception $e) {
                    \Log::error('Dashboard: Database error in zonesByStatus query', [
                        'error' => $e->getMessage(),
                        'user_id' => auth()->id(),
                    ]);
                    $zonesByStatus = [];
                }

                try {
                    $nodesByStatusQuery = DeviceNode::query();
                    if (! $user->isAdmin()) {
                        $nodesByStatusQuery->whereIn('id', $accessibleNodeIds ?: [0]);
                    }
                    $nodesByStatus = $nodesByStatusQuery
                        ->selectRaw('status, COUNT(*) as count')
                        ->groupBy('status')
                        ->pluck('count', 'status')
                        ->toArray();
                } catch (\Exception $e) {
                    \Log::error('Dashboard: Database error in nodesByStatus query', [
                        'error' => $e->getMessage(),
                        'user_id' => auth()->id(),
                    ]);
                    $nodesByStatus = [];
                }

                try {
                    $problematicZonesQuery = Zone::query()
                        ->select(['zones.id', 'zones.name', 'zones.status', 'zones.description', 'zones.greenhouse_id'])
                        ->leftJoin('alerts', function ($join) {
                            $join->on('alerts.zone_id', '=', 'zones.id')
                                ->where('alerts.status', '=', 'ACTIVE');
                        })
                        ->where(function ($q) {
                            $q->whereIn('zones.status', ['ALARM', 'WARNING'])
                                ->orWhereNotNull('alerts.id');
                        });
                    if (! $user->isAdmin()) {
                        $problematicZonesQuery->whereIn('zones.id', $accessibleZoneIds ?: [0]);
                    }
                    $problematicZones = $problematicZonesQuery
                        ->selectRaw('COUNT(DISTINCT alerts.id) as alerts_count')
                        ->groupBy('zones.id', 'zones.name', 'zones.status', 'zones.description', 'zones.greenhouse_id')
                        ->orderByRaw("CASE zones.status WHEN 'ALARM' THEN 1 WHEN 'WARNING' THEN 2 ELSE 3 END")
                        ->orderBy('alerts_count', 'desc')
                        ->limit(5)
                        ->with('greenhouse:id,name')
                        ->get();
                } catch (\Exception $e) {
                    \Log::error('Dashboard: Database error in problematicZones query', [
                        'error' => $e->getMessage(),
                        'user_id' => auth()->id(),
                    ]);
                    $problematicZones = collect([]);
                }

                try {
                    $zoneStatusRowsQuery = Zone::query()
                        ->select('greenhouse_id', 'status', DB::raw('COUNT(*) as count'));
                    if (! $user->isAdmin()) {
                        $zoneStatusRowsQuery->whereIn('id', $accessibleZoneIds ?: [0]);
                    }
                    $zoneStatusRows = $zoneStatusRowsQuery
                        ->groupBy('greenhouse_id', 'status')
                        ->get();

                    $zonesByGreenhouse = [];
                    foreach ($zoneStatusRows as $row) {
                        $zonesByGreenhouse[$row->greenhouse_id][$row->status] = (int) $row->count;
                    }
                } catch (\Exception $e) {
                    \Log::error('Dashboard: Database error in zonesByGreenhouse query', [
                        'error' => $e->getMessage(),
                        'user_id' => auth()->id(),
                    ]);
                    $zonesByGreenhouse = [];
                }

                try {
                    $nodesStatusRowsQuery = DeviceNode::query()
                        ->select('zones.greenhouse_id', 'nodes.status', DB::raw('COUNT(*) as count'))
                        ->join('zones', 'zones.id', '=', 'nodes.zone_id');
                    if (! $user->isAdmin()) {
                        $nodesStatusRowsQuery->whereIn('nodes.id', $accessibleNodeIds ?: [0]);
                    }
                    $nodesStatusRows = $nodesStatusRowsQuery
                        ->groupBy('zones.greenhouse_id', 'nodes.status')
                        ->get();

                    $nodesByGreenhouse = [];
                    foreach ($nodesStatusRows as $row) {
                        $nodesByGreenhouse[$row->greenhouse_id][$row->status] = (int) $row->count;
                    }
                } catch (\Exception $e) {
                    \Log::error('Dashboard: Database error in nodesByGreenhouse query', [
                        'error' => $e->getMessage(),
                        'user_id' => auth()->id(),
                    ]);
                    $nodesByGreenhouse = [];
                }

                try {
                    $alertsByGreenhouseQuery = Alert::query()
                        ->select('zones.greenhouse_id', DB::raw('COUNT(*) as count'))
                        ->join('zones', 'zones.id', '=', 'alerts.zone_id')
                        ->where('alerts.status', 'ACTIVE');
                    if (! $user->isAdmin()) {
                        $alertsByGreenhouseQuery->whereIn('alerts.zone_id', $accessibleZoneIds ?: [0]);
                    }
                    $alertsByGreenhouse = $alertsByGreenhouseQuery
                        ->groupBy('zones.greenhouse_id')
                        ->pluck('count', 'greenhouse_id')
                        ->toArray();
                } catch (\Exception $e) {
                    \Log::error('Dashboard: Database error in alertsByGreenhouse query', [
                        'error' => $e->getMessage(),
                        'user_id' => auth()->id(),
                    ]);
                    $alertsByGreenhouse = [];
                }

                try {
                    $greenhousesQuery = Greenhouse::query()
                        ->select(['id', 'uid', 'name', 'type', 'description']);
                    if (! $user->isAdmin()) {
                        // Согласно ZoneAccessHelper, все пользователи имеют доступ ко всем зонам/теплицам
                        // Показываем все теплицы, включая те, у которых ещё нет зон
                        // В будущем, при реализации мульти-тенантности, здесь будет фильтрация через user_greenhouses
                        $greenhousesQuery->where(function ($q) use ($accessibleZoneIds) {
                            // Теплицы с доступными зонами
                            $q->whereHas('zones', function ($zoneQuery) use ($accessibleZoneIds) {
                                $zoneQuery->whereIn('id', $accessibleZoneIds ?: [0]);
                            })
                            // ИЛИ теплицы без зон (чтобы новые теплицы тоже отображались)
                            ->orWhereDoesntHave('zones');
                        });
                    }
                    $greenhouses = $greenhousesQuery
                        ->withCount([
                            'zones' => function ($q) use ($user, $accessibleZoneIds) {
                                if (! $user->isAdmin()) {
                                    $q->whereIn('id', $accessibleZoneIds ?: [0]);
                                }
                            },
                            'zones as zones_running' => function ($q) use ($user, $accessibleZoneIds) {
                                $q->where('status', 'RUNNING');
                                if (! $user->isAdmin()) {
                                    $q->whereIn('id', $accessibleZoneIds ?: [0]);
                                }
                            },
                        ])
                        ->get()
                        ->map(function ($greenhouse) use ($zonesByGreenhouse, $nodesByGreenhouse, $alertsByGreenhouse) {
                            $greenhouse->zone_status_summary = $zonesByGreenhouse[$greenhouse->id] ?? [];
                            $greenhouse->node_status_summary = $nodesByGreenhouse[$greenhouse->id] ?? [];
                            $greenhouse->alerts_count = $alertsByGreenhouse[$greenhouse->id] ?? 0;

                            return $greenhouse;
                        });
                } catch (\Exception $e) {
                    \Log::error('Dashboard: Database error in greenhouses query', [
                        'error' => $e->getMessage(),
                        'user_id' => auth()->id(),
                    ]);
                    $greenhouses = collect([]);
                }

                try {
                    $latestAlertsQuery = Alert::query()
                        ->select(['id', 'type', 'status', 'details', 'zone_id', 'created_at'])
                        ->with('zone:id,name')
                        ->where('status', 'ACTIVE');
                    if (! $user->isAdmin()) {
                        $latestAlertsQuery->whereIn('zone_id', $accessibleZoneIds ?: [0]);
                    }
                    $latestAlerts = $latestAlertsQuery
                        ->latest('id')
                        ->limit(10)
                        ->get();
                } catch (\Exception $e) {
                    \Log::error('Dashboard: Database error in latestAlerts query', [
                        'error' => $e->getMessage(),
                        'user_id' => auth()->id(),
                    ]);
                    $latestAlerts = collect([]);
                }

                try {
                    $zonesForTelemetryQuery = Zone::query()
                        ->select(['id', 'name', 'status', 'greenhouse_id'])
                        ->with('greenhouse:id,name');
                    if (! $user->isAdmin()) {
                        $zonesForTelemetryQuery->whereIn('id', $accessibleZoneIds ?: [0]);
                    }
                    $zonesForTelemetry = $zonesForTelemetryQuery
                        ->orderByRaw("
                            CASE status
                                WHEN 'ALARM' THEN 1
                                WHEN 'WARNING' THEN 2
                                WHEN 'RUNNING' THEN 3
                                WHEN 'PAUSED' THEN 4
                                ELSE 5
                            END
                        ")
                        ->orderBy('name')
                        ->limit(20)
                        ->get();
                } catch (\Exception $e) {
                    \Log::error('Dashboard: Database error in zonesForTelemetry query', [
                        'error' => $e->getMessage(),
                        'user_id' => auth()->id(),
                    ]);
                    $zonesForTelemetry = collect([]);
                }

                return [
                    'greenhousesCount' => (int) ($stats->greenhouses_count ?? 0),
                    'zonesCount' => (int) ($stats->zones_count ?? 0),
                    'devicesCount' => (int) ($stats->devices_count ?? 0),
                    'alertsCount' => (int) ($stats->alerts_count ?? 0),
                    'zonesByStatus' => $zonesByStatus,
                    'nodesByStatus' => $nodesByStatus,
                    'problematicZones' => $problematicZones,
                    'greenhouses' => $greenhouses,
                    'zones' => $zonesForTelemetry,
                    'latestAlerts' => $latestAlerts,
                ];
            });
        } catch (\Exception $e) {
            // Если произошла критическая ошибка (например, проблема с кешем), возвращаем пустые данные
            \Log::error('Dashboard: Critical error', [
                'error' => $e->getMessage(),
                'user_id' => auth()->id(),
            ]);
            $dashboard = [
                'greenhousesCount' => 0,
                'zonesCount' => 0,
                'devicesCount' => 0,
                'alertsCount' => 0,
                'zonesByStatus' => [],
                'nodesByStatus' => [],
                'problematicZones' => [],
                'greenhouses' => [],
                'zones' => [],
                'latestAlerts' => [],
            ];
        }

        return Inertia::render('Dashboard/Index', [
            'auth' => ['user' => ['role' => auth()->user()->role ?? 'viewer']],
            'dashboard' => $dashboard,
        ]);
    })->name('dashboard');

    /**
     * Setup Wizard - мастер настройки системы
     * Доступен только для администраторов для предотвращения случайного/злонамеренного изменения конфигурации
     */
    Route::get('/setup/wizard', function () {
        $user = auth()->user();
        if (! $user || ! $user->isAdmin()) {
            abort(403, 'Only administrators can access the setup wizard');
        }

        return Inertia::render('Setup/Wizard', [
            'auth' => ['user' => ['role' => $user->role ?? 'admin']],
        ]);
    })->name('setup.wizard')->middleware('admin');

    /**
     * Greenhouses Index - список всех теплиц
     */
    Route::get('/greenhouses', function () {
        $user = auth()->user();
        $accessibleZoneIds = \App\Helpers\ZoneAccessHelper::getAccessibleZoneIds($user);
        
        try {
            $greenhousesQuery = Greenhouse::query()
                ->select(['id', 'uid', 'name', 'type', 'description', 'timezone', 'created_at']);
            
            if (! $user->isAdmin()) {
                // Показываем все теплицы, включая те, у которых ещё нет зон
                $greenhousesQuery->where(function ($q) use ($accessibleZoneIds) {
                    $q->whereHas('zones', function ($zoneQuery) use ($accessibleZoneIds) {
                        $zoneQuery->whereIn('id', $accessibleZoneIds ?: [0]);
                    })
                    ->orWhereDoesntHave('zones');
                });
            }
            
            $greenhouses = $greenhousesQuery
                ->withCount([
                    'zones' => function ($q) use ($user, $accessibleZoneIds) {
                        if (! $user->isAdmin()) {
                            $q->whereIn('id', $accessibleZoneIds ?: [0]);
                        }
                    },
                    'zones as zones_running' => function ($q) use ($user, $accessibleZoneIds) {
                        $q->where('status', 'RUNNING');
                        if (! $user->isAdmin()) {
                            $q->whereIn('id', $accessibleZoneIds ?: [0]);
                        }
                    },
                ])
                ->orderBy('created_at', 'desc')
                ->get();
        } catch (\Exception $e) {
            \Log::error('Greenhouses index: Database error', [
                'error' => $e->getMessage(),
                'user_id' => auth()->id(),
            ]);
            $greenhouses = collect([]);
        }
        
        return Inertia::render('Greenhouses/Index', [
            'auth' => ['user' => ['role' => auth()->user()->role ?? 'viewer']],
            'greenhouses' => $greenhouses,
        ]);
    })->name('greenhouses.index');

    /**
     * Create Greenhouse - создание теплицы
     */
    Route::get('/greenhouses/create', function () {
        return Inertia::render('Greenhouses/Create', [
            'auth' => ['user' => ['role' => auth()->user()->role ?? 'viewer']],
        ]);
    })->name('greenhouses.create');

    /**
     * Greenhouse Show - детальная страница теплицы
     */
    Route::get('/greenhouses/{greenhouse}', function (Greenhouse $greenhouse) {
        $zones = Zone::query()
            ->where('greenhouse_id', $greenhouse->id)
            ->with([
                'activeGrowCycle.recipeRevision.recipe:id,name,description',
                'activeGrowCycle.currentPhase',
                'activeGrowCycle.plant:id,name',
            ])
            ->withCount([
                'alerts as alerts_count',
                'nodes as nodes_total',
                'nodes as nodes_online' => function ($query) {
                    $query->where('status', 'online');
                },
                'nodes as nodes_offline' => function ($query) {
                    $query->where('status', 'offline');
                },
            ])
            ->orderBy('status')
            ->get();

        $zoneIds = $zones->pluck('id')->toArray();

        $telemetryByZone = [];
        if (! empty($zoneIds)) {
            // Запрос к telemetry_last с join на sensors для получения zone_id и типа метрики
            $telemetryAll = TelemetryLast::query()
                ->join('sensors', 'telemetry_last.sensor_id', '=', 'sensors.id')
                ->whereIn('sensors.zone_id', $zoneIds)
                ->whereNotNull('sensors.zone_id')
                ->select([
                    'sensors.zone_id',
                    'sensors.type as metric_type',
                    'telemetry_last.last_value as value'
                ])
                ->get();

            foreach ($telemetryAll as $metric) {
                $key = strtolower($metric->metric_type ?? '');
                if (! isset($telemetryByZone[$metric->zone_id])) {
                    $telemetryByZone[$metric->zone_id] = [
                        'ph' => null,
                        'ec' => null,
                        'temperature' => null,
                        'humidity' => null,
                    ];
                }

                if ($key === 'ph') {
                    $telemetryByZone[$metric->zone_id]['ph'] = (float) $metric->value;
                } elseif ($key === 'ec') {
                    $telemetryByZone[$metric->zone_id]['ec'] = (float) $metric->value;
                } elseif ($key === 'temperature') {
                    $telemetryByZone[$metric->zone_id]['temperature'] = (float) $metric->value;
                } elseif ($key === 'humidity') {
                    $telemetryByZone[$metric->zone_id]['humidity'] = (float) $metric->value;
                }
            }
        }

        $zones->each(function (Zone $zone) use ($telemetryByZone) {
            $zone->telemetry = $telemetryByZone[$zone->id] ?? null;
        });

        $nodes = DeviceNode::query()
            ->whereIn('zone_id', $zoneIds)
            ->with('zone:id,name')
            ->orderByDesc('last_seen_at')
            ->get();

        $nodesTotals = DeviceNode::query()
            ->whereIn('zone_id', $zoneIds)
            ->select([
                DB::raw('COUNT(*) as total'),
                DB::raw("SUM(CASE WHEN status = 'online' THEN 1 ELSE 0 END) as online"),
                DB::raw("SUM(CASE WHEN status = 'offline' THEN 1 ELSE 0 END) as offline"),
            ])
            ->first();

        $nodeSummary = [
            'total' => $nodesTotals->total ?? 0,
            'online' => $nodesTotals->online ?? 0,
            'offline' => $nodesTotals->offline ?? 0,
        ];

        $activeAlerts = $zones->sum('alerts_count');

        return Inertia::render('Greenhouses/Show', [
            'auth' => ['user' => ['role' => auth()->user()->role ?? 'viewer']],
            'greenhouse' => $greenhouse,
            'zones' => $zones,
            'nodes' => $nodes,
            'nodeSummary' => $nodeSummary,
            'activeAlerts' => $activeAlerts,
        ]);
    })->name('greenhouses.show');

    /**
     * Cycle Center - основной операционный экран циклов выращивания
     */
    Route::get('/cycles', [\App\Http\Controllers\CycleCenterController::class, 'index'])->name('cycles.center');

    /**
     * Grow Cycle Wizard - мастер запуска цикла выращивания
     *
     * Inertia Props:
     * - auth: { user: { role: 'viewer'|'operator'|'admin'|'agronomist' } }
     */
    Route::get('/grow-cycle-wizard', function () {
        return Inertia::render('GrowCycles/Wizard', [
            'auth' => ['user' => ['role' => auth()->user()->role ?? 'viewer']],
        ]);
    })->name('grow-cycle-wizard');

    /**
     * Analytics - страница аналитики и отчетов
     *
     * Inertia Props:
     * - auth: { user: { role: 'viewer'|'operator'|'admin'|'agronomist' } }
     */
    Route::get('/analytics', function () {
        return Inertia::render('Analytics/Index', [
            'auth' => ['user' => ['role' => auth()->user()->role ?? 'viewer']],
        ]);
    })->name('analytics');

    /**
     * End of routes
     */
});
