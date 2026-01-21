<?php

use App\Http\Controllers\CycleCenterController;
use App\Http\Controllers\PlantController;
use App\Http\Controllers\ProfileController;
use App\Models\Alert;
use App\Models\DeviceNode;
use App\Models\Greenhouse;
use App\Models\GrowCycle;
use App\Models\Recipe;
use App\Models\SystemLog;
use App\Models\TelemetryLast;
use App\Models\Zone;
use Illuminate\Http\Request;
use Illuminate\Support\Facades\Auth;
use Illuminate\Support\Facades\Broadcast;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Route;
use Inertia\Inertia;

// Роут для Laravel Boost browser-logs
// В проде отключен для предотвращения DoS и утечки данных
// В dev режиме принимает Boost payload без auth
Route::match(['GET', 'POST'], '/_boost/browser-logs', function (\Illuminate\Http\Request $request) {
    if (app()->environment('production')) {
        \Log::warning('Browser log endpoint accessed in production (blocked)', [
            'ip' => $request->ip(),
            'user_agent' => $request->userAgent(),
            'method' => $request->method(),
        ]);

        return response()->json(['status' => 'disabled'], 404);
    }

    if ($request->isMethod('GET')) {
        return response()->json(['status' => 'ok', 'method' => 'GET'], 200);
    }

    $allowAnonymous = app()->environment(['local', 'testing']) || config('app.debug', false) === true;
    if (! $allowAnonymous && ! auth()->check()) {
        \Log::warning('Browser log endpoint: unauthenticated request', [
            'ip' => $request->ip(),
            'user_agent' => $request->userAgent(),
            'method' => $request->method(),
        ]);

        return response()->json(['status' => 'unauthorized'], 403);
    }

    $buildLogMessage = function (array $data) use (&$buildLogMessage): string {
        $messages = [];

        foreach ($data as $value) {
            $messages[] = match (true) {
                is_array($value) => $buildLogMessage($value),
                is_string($value), is_numeric($value) => (string) $value,
                is_bool($value) => $value ? 'true' : 'false',
                is_null($value) => 'null',
                is_object($value) => json_encode($value) ?: '',
                default => (string) $value,
            };
        }

        return implode(' ', array_filter($messages, static fn ($message): bool => $message !== ''));
    };

    try {
        $logger = \Log::channel('browser');
    } catch (\Throwable $e) {
        $logger = \Log::channel((string) config('logging.default'));
    }

    if (is_array($request->input('logs'))) {
        $validated = $request->validate([
            'logs' => ['required', 'array', 'max:200'],
            'logs.*.type' => ['nullable', 'string', 'max:50'],
            'logs.*.timestamp' => ['nullable', 'string', 'max:64'],
            'logs.*.data' => ['nullable', 'array', 'max:50'],
            'logs.*.url' => ['nullable', 'string', 'max:2000'],
            'logs.*.userAgent' => ['nullable', 'string', 'max:1000'],
        ]);

        foreach ($validated['logs'] as $log) {
            $logType = $log['type'] ?? 'log';
            $level = match ($logType) {
                'warn' => 'warning',
                'log', 'table' => 'debug',
                'window_error', 'uncaught_error', 'unhandled_rejection' => 'error',
                'debug', 'info', 'notice', 'warning', 'error', 'critical', 'alert', 'emergency' => $logType,
                default => 'info',
            };
            $message = $buildLogMessage($log['data'] ?? []);
            $context = [
                'url' => $log['url'] ?? $request->fullUrl(),
                'user_agent' => $log['userAgent'] ?? $request->userAgent(),
                'timestamp' => $log['timestamp'] ?? now()->toIso8601String(),
            ];

            if (auth()->check()) {
                $context['user_id'] = auth()->id();
            }

            $logger->write(
                level: $level,
                message: $message !== '' ? $message : '[empty]',
                context: $context
            );
        }

        return response()->json(['status' => 'ok', 'count' => count($validated['logs'])], 200);
    }

    $validated = $request->validate([
        'level' => ['nullable', 'string', 'in:log,info,warn,error'],
        'message' => ['nullable', 'string', 'max:1000'],
        'data' => ['nullable', 'array', 'max:10'],
    ]);

    \Log::debug('Browser log received (dev only)', [
        'user_id' => auth()->id(),
        'level' => $validated['level'] ?? 'log',
        'message' => $validated['message'] ?? null,
        'data_keys' => isset($validated['data']) ? array_keys($validated['data']) : [],
    ]);

    return response()->json(['status' => 'ok'], 200);
})->middleware(['web', 'throttle:120,1']); // 120 запросов в минуту для dev режима

// Broadcasting authentication route
// Rate limiting: 300 запросов в минуту для поддержки множественных каналов и переподключений
// Поддерживает как сессионную авторизацию (web guard), так и токеновую (Sanctum PAT)
Route::post('/broadcasting/auth', function (\Illuminate\Http\Request $request) {
    try {
        // Сначала пытаемся аутентифицировать через Sanctum PAT (для мобильных/SPA клиентов)
        // Это позволяет использовать токен из /api/auth/login для WebSocket авторизации
        $user = null;

        // Проверяем Sanctum токен из заголовка Authorization
        if ($request->bearerToken()) {
            $token = \Laravel\Sanctum\PersonalAccessToken::findToken($request->bearerToken());
            if ($token && $token->tokenable) {
                // Проверяем срок действия токена
                if ($token->expires_at && $token->expires_at->isPast()) {
                    \Log::warning('Broadcasting auth: Sanctum token expired', [
                        'ip' => $request->ip(),
                        'token_id' => $token->id,
                    ]);

                    return response()->json(['message' => 'Token expired.'], 403);
                }

                $user = $token->tokenable;
                // Устанавливаем пользователя для обоих guard'ов
                \Illuminate\Support\Facades\Auth::guard('sanctum')->setUser($user);
                \Illuminate\Support\Facades\Auth::guard('web')->setUser($user);
                $request->setUserResolver(static fn () => $user);

                // Обновляем last_used_at для отслеживания активности токена
                $token->forceFill(['last_used_at' => now()])->save();

                \Log::debug('Broadcasting auth: Authenticated via Sanctum PAT', [
                    'user_id' => $user->id,
                    'channel' => $request->input('channel_name'),
                ]);
            }
        }

        // Если не удалось аутентифицировать через токен, проверяем сессию (web guard)
        if (! $user) {
            if (! auth()->check() && ! auth('web')->check()) {
                \Log::warning('Broadcasting auth: Unauthenticated request', [
                    'ip' => $request->ip(),
                    'user_agent' => $request->userAgent(),
                    'channel' => $request->input('channel_name'),
                    'has_bearer_token' => $request->bearerToken() !== null,
                ]);

                return response()->json(['message' => 'Unauthenticated.'], 403);
            }
            $user = auth()->user() ?? auth('web')->user();
        }

        \Log::debug('Broadcasting auth: Starting authorization', [
            'channel' => $request->input('channel_name'),
            'user_authenticated' => $user !== null,
            'auth_method' => $request->bearerToken() ? 'sanctum_token' : 'session',
        ]);

        if (! $user) {
            \Log::error('Broadcasting auth: User is null after authentication attempts', [
                'ip' => $request->ip(),
                'channel' => $request->input('channel_name'),
            ]);

            return response()->json(['message' => 'Unauthenticated.'], 403);
        }

        $channelName = $request->input('channel_name');

        \Log::debug('Broadcasting auth: Authorizing channel', [
            'user_id' => $user->id,
            'channel' => $channelName,
        ]);

        // Обрабатываем ошибки БД отдельно
        try {
            $response = Broadcast::auth($request);

            // Проверяем, что ответ валиден
            if (! $response) {
                \Log::warning('Broadcasting auth: Broadcast::auth returned null', [
                    'user_id' => $user->id,
                    'channel' => $channelName,
                ]);

                return response()->json(['message' => 'Authorization failed.'], 403);
            }

            return $response;
        } catch (\Illuminate\Database\QueryException $dbException) {
            $isDev = app()->environment(['local', 'testing', 'development']);
            $errorMessage = $dbException->getMessage();
            $isMissingTable = str_contains($errorMessage, 'no such table') ||
                             str_contains($errorMessage, "doesn't exist") ||
                             str_contains($errorMessage, 'relation does not exist');

            if ($isDev) {
                \Log::error('Broadcasting auth: Database error', [
                    'user_id' => $user->id,
                    'channel' => $channelName,
                    'error' => $errorMessage,
                    'sql_state' => $dbException->getCode(),
                    'is_missing_table' => $isMissingTable,
                ]);
            } else {
                \Log::error('Broadcasting auth: Database error', [
                    'user_id' => $user->id,
                    'channel' => $channelName,
                    'error_type' => $isMissingTable ? 'missing_table' : 'connection_error',
                ]);
            }

            if ($isDev) {
                if ($isMissingTable) {
                    return response()->json([
                        'message' => 'Database schema not initialized. Please run migrations.',
                        'error' => 'Missing database table',
                        'hint' => 'Run: php artisan migrate',
                    ], 503);
                }

                return response()->json([
                    'message' => 'Service temporarily unavailable. Please check database connection.',
                    'error' => 'Database connection error',
                ], 503);
            } else {
                return response()->json([
                    'message' => 'Service temporarily unavailable.',
                ], 503);
            }
        } catch (\PDOException $pdoException) {
            $isDev = app()->environment(['local', 'testing', 'development']);

            if ($isDev) {
                \Log::error('Broadcasting auth: PDO error', [
                    'user_id' => $user->id ?? null,
                    'channel' => $channelName ?? null,
                    'error' => $pdoException->getMessage(),
                    'code' => $pdoException->getCode(),
                ]);
            } else {
                \Log::error('Broadcasting auth: PDO error', [
                    'user_id' => $user->id ?? null,
                    'channel' => $channelName ?? null,
                    'error_type' => 'pdo_connection_error',
                ]);
            }

            if ($isDev) {
                return response()->json([
                    'message' => 'Database connection error. Please check database configuration.',
                    'error' => 'PDO error',
                ], 503);
            } else {
                return response()->json([
                    'message' => 'Service temporarily unavailable.',
                ], 503);
            }
        }

        \Log::debug('Broadcasting auth: Success', [
            'user_id' => $user->id,
            'channel' => $channelName,
            'status' => $response->getStatusCode(),
        ]);

        return $response;
    } catch (\Illuminate\Broadcasting\BroadcastException $broadcastException) {
        // Отказ в доступе к каналу - возвращаем 403, а не 500
        \Log::warning('Broadcasting auth: Channel authorization denied', [
            'user_id' => auth()->id(),
            'channel' => $request->input('channel_name'),
            'error' => $broadcastException->getMessage(),
        ]);

        return response()->json(['message' => 'Unauthorized.'], 403);
    } catch (\Exception $e) {
        $isDev = app()->environment(['local', 'testing', 'development']);

        if ($isDev) {
            \Log::error('Broadcasting auth: Error', [
                'user_id' => auth()->id(),
                'error' => $e->getMessage(),
                'trace' => $e->getTraceAsString(),
            ]);
        } else {
            \Log::error('Broadcasting auth: Error', [
                'user_id' => auth()->id(),
                'error' => $e->getMessage(),
            ]);
        }

        return response()->json(['message' => 'Authorization failed.'], 500);
    }
})->middleware(['web', 'throttle:300,1'])->withoutMiddleware([\App\Http\Middleware\HandleInertiaRequests::class]); // Rate limiting: 300 запросов в минуту для поддержки множественных каналов и переподключений

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
                    'telemetry_last.last_value as value',
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
    Route::get('/cycles', [CycleCenterController::class, 'index'])->name('cycles.center');

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
     * Zones routes
     */
    Route::prefix('zones')->group(function () {
        /**
         * Zones Index - список всех зон
         *
         * Inertia Props:
         * - auth: { user: { role: 'viewer'|'operator'|'admin' } }
         * - zones: Array<{
         *     id: int,
         *     name: string,
         *     status: 'RUNNING'|'PAUSED'|'WARNING'|'ALARM',
         *     description: string,
         *     greenhouse_id: int,
         *     greenhouse: { id: int, name: string },
         *     telemetry: { ph: float|null, ec: float|null, temperature: float|null, humidity: float|null }
         *   }>
         *
         * Кеширование: 10 секунд
         * Telemetry: batch loading для всех зон
         */
        Route::get('/', function () {
            // Кешируем список зон на 10 секунд
            $cacheKey = 'zones_list_'.auth()->id();
            $zones = \Illuminate\Support\Facades\Cache::remember($cacheKey, 10, function () {
                return Zone::query()
                    ->select(['id', 'name', 'status', 'description', 'greenhouse_id'])
                    ->with([
                        'greenhouse:id,name',
                        'activeGrowCycle.recipeRevision.recipe:id,name',
                        'activeGrowCycle.recipeRevision.phases',
                        'activeGrowCycle.currentPhase',
                        'activeGrowCycle.phases',
                        'activeGrowCycle.plant:id,name',
                    ])
                    ->get();
            });

            // Загружаем telemetry для всех зон (batch loading)
            $zoneIds = $zones->pluck('id')->toArray();
            $telemetryByZone = [];

            if (! empty($zoneIds)) {
                // Запрос к telemetry_last с join на sensors для получения zone_id и типа метрики
                $telemetryAll = \App\Models\TelemetryLast::query()
                    ->join('sensors', 'telemetry_last.sensor_id', '=', 'sensors.id')
                    ->whereIn('sensors.zone_id', $zoneIds)
                    ->whereNotNull('sensors.zone_id')
                    ->select([
                        'sensors.zone_id',
                        'sensors.type as metric_type',
                        'telemetry_last.last_value as value',
                    ])
                    ->get();

                // Группируем по zone_id и преобразуем в формат {ph, ec, temperature, humidity}
                $telemetryByZone = $telemetryAll->groupBy('zone_id')->map(function ($metrics) {
                    $result = ['ph' => null, 'ec' => null, 'temperature' => null, 'humidity' => null];
                    foreach ($metrics as $metric) {
                        $key = strtolower($metric->metric_type ?? '');
                        if ($key === 'ph') {
                            $result['ph'] = $metric->value;
                        } elseif ($key === 'ec') {
                            $result['ec'] = $metric->value;
                        } elseif ($key === 'temperature') {
                            $result['temperature'] = $metric->value;
                        } elseif ($key === 'humidity') {
                            $result['humidity'] = $metric->value;
                        }
                    }

                    return $result;
                })->toArray();
            }

            // Добавляем telemetry к каждой зоне
            $zonesWithTelemetry = $zones->map(function ($zone) use ($telemetryByZone) {
                $zone->telemetry = $telemetryByZone[$zone->id] ?? null;

                return $zone;
            });

            return Inertia::render('Zones/Index', [
                'auth' => ['user' => ['role' => auth()->user()->role ?? 'viewer']],
                'zones' => $zonesWithTelemetry,
            ]);
        })->name('zones.web.index');

        /**
         * Zone Show - детальная страница зоны
         *
         * Inertia Props:
         * - auth: { user: { role: 'viewer'|'operator'|'admin' } }
         * - zoneId: int
         * - zone: {
         *     id: int,
         *     name: string,
         *     status: 'RUNNING'|'PAUSED'|'WARNING'|'ALARM',
         *     description: string,
         *     greenhouse_id: int,
         *     greenhouse: { id: int, name: string },
         *     recipeInstance: {
         *       recipe: { id: int, name: string },
         *       current_phase_index: int
         *     }
         *   }
         * - telemetry: { ph: float|null, ec: float|null, temperature: float|null, humidity: float|null }
         * - targets: Object - «сырые» цели текущей фазы рецепта (исторический формат, для back-compat)
         * - current_phase: {
         *     index: int,
         *     name: string|null,
         *     duration_hours: float|null,
         *     phase_started_at: string|null, // UTC ISO8601
         *     phase_ends_at: string|null,    // UTC ISO8601
         *     targets: {
         *       ph: { min: float|null, max: float|null }|null,
         *       ec: { min: float|null, max: float|null }|null,
         *       climate: { temperature: float|null, humidity: float|null }|null,
         *       lighting: { hours_on: float|null, hours_off: float|null }|null,
         *       irrigation: { interval_minutes: float|null, duration_seconds: float|null }|null
         *     }|null
         *   }|null
         * - active_cycle: {
         *     id: int,
         *     type: 'GROWTH_CYCLE',
         *     status: 'active'|'finished'|'aborted',
         *     started_at: string, // UTC ISO8601
         *     ends_at: string,    // UTC ISO8601
         *     subsystems: {
         *       ph: { required: bool, enabled: bool, targets: { min: float|null, max: float|null }|null },
         *       ec: { required: bool, enabled: bool, targets: { min: float|null, max: float|null }|null },
         *       climate: { required: bool, enabled: bool, targets: { temperature: float|null, humidity: float|null }|null },
         *       lighting: { required: bool, enabled: bool, targets: { hours_on: float|null, hours_off: float|null }|null },
         *       irrigation: { required: bool, enabled: bool, targets: { interval_minutes: float|null, duration_seconds: float|null }|null }
         *     }
         *   }|null
         * - devices: Array<{ id, uid, zone_id, name, type, status, fw_version, last_seen_at, zone }>
         * - events: Array<{ id, kind: 'ALERT'|'WARNING'|'INFO', message: string, occurred_at: ISO8601 }>
         * - cycles: {
         *     PH_CONTROL: { type, strategy, interval, last_run, next_run },
         *     EC_CONTROL: { type, strategy, interval, last_run, next_run },
         *     IRRIGATION: { type, strategy, interval, last_run, next_run },
         *     LIGHTING: { type, strategy, interval, last_run, next_run },
         *     CLIMATE: { type, strategy, interval, last_run, next_run }
         *   }
         */
        Route::get('/{zoneId}', function (string $zoneId) {
            // Convert zoneId to integer
            $zoneIdInt = (int) $zoneId;

            // Загружаем зону с активным циклом выращивания
            // ВАЖНО: Используем fresh() чтобы получить свежие данные из БД
            $zone = Zone::query()
                ->with([
                    'greenhouse:id,name',
                    'activeGrowCycle.recipeRevision.recipe:id,name,description',
                    'activeGrowCycle.recipeRevision.phases',
                    'activeGrowCycle.currentPhase',
                    'activeGrowCycle.phases',
                    'activeGrowCycle.plant:id,name',
                ])
                ->findOrFail($zoneIdInt);

            // Обновляем зону, чтобы гарантировать загрузку свежих данных
            $zone->refresh();
            $zone->loadMissing([
                'activeGrowCycle.recipeRevision.recipe',
                'activeGrowCycle.recipeRevision.phases',
                'activeGrowCycle.currentPhase',
                'activeGrowCycle.phases',
                'activeGrowCycle.plant',
            ]);

            // Логируем для отладки
            \Log::info('Loading zone for web route', [
                'zone_id' => $zoneIdInt,
                'has_active_grow_cycle' => $zone->activeGrowCycle !== null,
                'grow_cycle_id' => $zone->activeGrowCycle?->id,
                'recipe_revision_id' => $zone->activeGrowCycle?->recipe_revision_id,
                'recipe_name' => $zone->activeGrowCycle?->recipeRevision?->recipe?->name,
            ]);

            // Загрузить телеметрию
            $telemetryLast = \App\Models\TelemetryLast::query()
                ->join('sensors', 'telemetry_last.sensor_id', '=', 'sensors.id')
                ->where('sensors.zone_id', $zoneIdInt)
                ->whereNotNull('sensors.zone_id')
                ->select([
                    'sensors.type as metric_type',
                    'telemetry_last.last_value as value',
                ])
                ->get()
                ->mapWithKeys(function ($item) {
                    $key = strtolower($item->metric_type ?? '');
                    if ($key === 'ph') {
                        return ['ph' => $item->value];
                    }
                    if ($key === 'ec') {
                        return ['ec' => $item->value];
                    }
                    if ($key === 'temperature') {
                        return ['temperature' => $item->value];
                    }
                    if ($key === 'humidity') {
                        return ['humidity' => $item->value];
                    }

                    return [];
                })
                ->toArray();

            // Загрузить эффективные цели через API
            $targets = [];
            $activeGrowCycle = $zone->activeGrowCycle;
            if ($activeGrowCycle) {
                try {
                    $effectiveTargetsService = app(\App\Services\EffectiveTargetsService::class);
                    $effectiveTargets = $effectiveTargetsService->getEffectiveTargets($activeGrowCycle->id);
                    $targets = $effectiveTargets['targets'] ?? [];
                } catch (\Exception $e) {
                    \Log::warning('Failed to get effective targets for zone show', [
                        'zone_id' => $zone->id,
                        'cycle_id' => $activeGrowCycle->id,
                        'error' => $e->getMessage(),
                    ]);
                }
            }

            // Нормализованный блок current_phase через effective targets
            $currentPhaseNormalized = null;
            $activeGrowCycle = $zone->activeGrowCycle;
            if ($activeGrowCycle) {
                try {
                    $effectiveTargetsService = app(\App\Services\EffectiveTargetsService::class);
                    $effectiveTargets = $effectiveTargetsService->getEffectiveTargets($activeGrowCycle->id);
                    $phase = $effectiveTargets['phase'] ?? null;

                    if ($phase) {
                        $currentPhaseNormalized = [
                            'index' => $phase['id'] ?? 0,
                            'name' => $phase['name'] ?? 'Неизвестная фаза',
                            'duration_hours' => 0, // Не доступно в новом API
                            'phase_started_at' => $phase['started_at'] ?? null,
                            'phase_ends_at' => $phase['due_at'] ?? null,
                            'targets' => $targets, // Используем уже загруженные targets
                        ];
                    }
                } catch (\Exception $e) {
                    \Log::warning('Failed to get current phase normalized', [
                        'zone_id' => $zone->id,
                        'cycle_id' => $activeGrowCycle->id,
                        'error' => $e->getMessage(),
                    ]);
                }
            }
            // Агрегированный цикл выращивания (один активный на зону).
            $activeCycleModel = GrowCycle::query()
                ->where('zone_id', $zone->id)
                ->whereIn('status', ['PLANNED', 'RUNNING', 'PAUSED'])
                ->latest('started_at')
                ->first();

            $activeCycle = null;
            if ($activeCycleModel) {
                $activeCycle = [
                    'id' => $activeCycleModel->id,
                    'type' => $activeCycleModel->type ?? 'GROWTH_CYCLE',
                    'status' => $activeCycleModel->status ?? 'active',
                    'started_at' => $activeCycleModel->started_at?->toIso8601String(),
                    'ends_at' => $activeCycleModel->ends_at?->toIso8601String(),
                    'subsystems' => $activeCycleModel->subsystems ?? [],
                ];
            }

            // Загрузить устройства зоны
            $devices = \App\Models\DeviceNode::query()
                ->select(['id', 'uid', 'zone_id', 'name', 'type', 'status', 'fw_version', 'last_seen_at'])
                ->where('zone_id', $zoneIdInt)
                ->with('zone:id,name')
                ->get();

            // Загрузить последние события зоны (если модель Event существует)
            $events = collect([]);
            if (class_exists(\App\Models\Event::class)) {
                try {
                    $eventsRaw = \App\Models\Event::query()
                        ->where('zone_id', $zoneIdInt)
                        ->select(['id', 'type', 'details', 'created_at'])
                        ->latest('created_at')
                        ->limit(20)
                        ->get();

                    // Маппинг структуры Events для фронтенда
                    // type → kind, details.message → message, created_at → occurred_at
                    $events = $eventsRaw->map(function ($event) {
                        $details = $event->details ?? [];
                        $message = $details['message'] ?? $details['msg'] ?? null;

                        // Специальное форматирование событий циклов выращивания, чтобы оператор видел параметры
                        if (str_starts_with($event->type ?? '', 'CYCLE_') && isset($details['subsystems']) && is_array($details['subsystems'])) {
                            $parts = [];
                            $subs = $details['subsystems'];

                            // pH (обязательный)
                            if (isset($subs['ph']['enabled']) && $subs['ph']['enabled'] === true && isset($subs['ph']['targets']) && is_array($subs['ph']['targets'])) {
                                $t = $subs['ph']['targets'];
                                if (isset($t['min']) && isset($t['max'])) {
                                    $parts[] = sprintf('pH %.1f–%.1f', (float) $t['min'], (float) $t['max']);
                                }
                            }

                            // EC (обязательный)
                            if (isset($subs['ec']['enabled']) && $subs['ec']['enabled'] === true && isset($subs['ec']['targets']) && is_array($subs['ec']['targets'])) {
                                $t = $subs['ec']['targets'];
                                if (isset($t['min']) && isset($t['max'])) {
                                    $parts[] = sprintf('EC %.1f–%.1f', (float) $t['min'], (float) $t['max']);
                                }
                            }

                            // Климат (опциональный)
                            if (isset($subs['climate']['enabled']) && $subs['climate']['enabled'] === true && isset($subs['climate']['targets']) && is_array($subs['climate']['targets'])) {
                                $t = $subs['climate']['targets'];
                                if (isset($t['temperature']) && isset($t['humidity'])) {
                                    $parts[] = sprintf('Климат t=%.1f°C, RH=%.0f%%', (float) $t['temperature'], (float) $t['humidity']);
                                }
                            }

                            // Освещение (опциональный)
                            if (isset($subs['lighting']['enabled']) && $subs['lighting']['enabled'] === true && isset($subs['lighting']['targets']) && is_array($subs['lighting']['targets'])) {
                                $t = $subs['lighting']['targets'];
                                if (isset($t['hours_on']) && isset($t['hours_off'])) {
                                    $parts[] = sprintf('Свет %.1fч / пауза %.1fч', (float) $t['hours_on'], (float) $t['hours_off']);
                                }
                            }

                            // Полив (обязательный)
                            if (isset($subs['irrigation']['enabled']) && $subs['irrigation']['enabled'] === true && isset($subs['irrigation']['targets']) && is_array($subs['irrigation']['targets'])) {
                                $t = $subs['irrigation']['targets'];
                                if (isset($t['interval_minutes']) && isset($t['duration_seconds'])) {
                                    $parts[] = sprintf('Полив каждые %d мин, %d с', (int) $t['interval_minutes'], (int) $t['duration_seconds']);
                                }
                            }

                            if (! empty($parts)) {
                                $message = implode('; ', $parts);
                            }
                        }

                        if (! $message) {
                            $message = $event->type ?? '';
                        }

                        return [
                            'id' => $event->id,
                            'kind' => $event->type ?? 'INFO',
                            'message' => $message,
                            'occurred_at' => $event->created_at ? $event->created_at->toIso8601String() : null,
                        ];
                    });
                } catch (\Exception $e) {
                    // Event model or table doesn't exist, use empty collection
                    $events = collect([]);
                }
            }

            // Загрузить данные cycles для зоны
            $cycles = [];
            try {
                $settings = $zone->settings ?? [];
                // Получаем последние команды для вычисления last_run
                $lastCommands = \App\Models\Command::query()
                    ->where('zone_id', $zoneIdInt)
                    ->whereIn('cmd', ['FORCE_PH_CONTROL', 'FORCE_EC_CONTROL', 'FORCE_IRRIGATION', 'FORCE_LIGHTING', 'FORCE_CLIMATE'])
                    ->whereNotNull('ack_at')
                    ->select(['cmd', 'ack_at'])
                    ->orderBy('ack_at', 'desc')
                    ->get()
                    ->groupBy('cmd')
                    ->map(function ($group) {
                        return $group->first()->ack_at?->toIso8601String();
                    });

                // Определяем интервалы из settings или targets
                $cycleConfigs = [
                    'PH_CONTROL' => [
                        'strategy' => $settings['ph_control']['strategy'] ?? 'periodic',
                        'interval' => $settings['ph_control']['interval_sec'] ?? 300,
                    ],
                    'EC_CONTROL' => [
                        'strategy' => $settings['ec_control']['strategy'] ?? 'periodic',
                        'interval' => $settings['ec_control']['interval_sec'] ?? 300,
                    ],
                    'IRRIGATION' => [
                        'strategy' => $settings['irrigation']['strategy'] ?? 'periodic',
                        'interval' => $targets['irrigation_interval_sec'] ?? $settings['irrigation']['interval_sec'] ?? null,
                    ],
                    'LIGHTING' => [
                        'strategy' => $settings['lighting']['strategy'] ?? 'periodic',
                        'interval' => isset($targets['light_hours']) ? $targets['light_hours'] * 3600 : ($settings['lighting']['interval_sec'] ?? null),
                    ],
                    'CLIMATE' => [
                        'strategy' => $settings['climate']['strategy'] ?? 'periodic',
                        'interval' => $settings['climate']['interval_sec'] ?? 300,
                    ],
                ];

                // Формируем ответ
                foreach ($cycleConfigs as $type => $config) {
                    $lastRun = $lastCommands->get("FORCE_{$type}");
                    $interval = $config['interval'];
                    $nextRun = null;

                    if ($lastRun && $interval) {
                        $nextRun = \Carbon\Carbon::parse($lastRun)->addSeconds($interval)->toIso8601String();
                    }

                    $cycles[$type] = [
                        'type' => $type,
                        'strategy' => $config['strategy'],
                        'interval' => $interval,
                        'last_run' => $lastRun,
                        'next_run' => $nextRun,
                    ];
                }
            } catch (\Exception $e) {
                // Если ошибка при загрузке cycles, используем пустой массив
                $cycles = [];
            }

            // Формируем данные для отправки в Inertia
            // ВАЖНО: Используем оригинальную модель, так как Inertia правильно сериализует отношения
            // Но убеждаемся, что все отношения загружены
            if (! $zone->relationLoaded('activeGrowCycle')) {
                $zone->load([
                    'activeGrowCycle.recipeRevision.recipe',
                    'activeGrowCycle.currentPhase',
                    'activeGrowCycle.phases',
                ]);
            }

            // Логируем данные перед отправкой в Inertia
            \Log::info('Sending zone data to Inertia', [
                'zone_id' => $zone->id,
                'zone_name' => $zone->name,
                'has_active_grow_cycle' => $zone->activeGrowCycle !== null,
                'grow_cycle' => $zone->activeGrowCycle ? [
                    'id' => $zone->activeGrowCycle->id,
                    'recipe_revision_id' => $zone->activeGrowCycle->recipe_revision_id,
                    'recipe_name' => $zone->activeGrowCycle->recipeRevision?->recipe?->name,
                    'current_phase_id' => $zone->activeGrowCycle->current_phase_id,
                ] : null,
            ]);

            return Inertia::render('Zones/Show', [
                'auth' => ['user' => ['role' => auth()->user()->role ?? 'viewer']],
                'zoneId' => $zoneIdInt,
                'zone' => $zone, // Используем модель - Inertia правильно сериализует отношения
                'telemetry' => $telemetryLast,
                'targets' => $targets,
                'current_phase' => $currentPhaseNormalized,
                'active_cycle' => $activeCycle,
                'active_grow_cycle' => $zone->activeGrowCycle,
                'devices' => $devices,
                'events' => $events,
                'cycles' => $cycles,
            ]);
        })->name('zones.show');
    });

    /**
     * Devices routes
     */
    Route::prefix('devices')->group(function () {
        /**
         * Devices Index - список всех устройств
         *
         * Inertia Props:
         * - auth: { user: { role: 'viewer'|'operator'|'admin' } }
         * - devices: Array<{
         *     id: int,
         *     uid: string,
         *     zone_id: int,
         *     name: string,
         *     type: string,
         *     status: string,
         *     fw_version: string,
         *     last_seen_at: datetime,
         *     zone: { id: int, name: string }
         *   }>
         *
         * Кеширование: 10 секунд
         */
        Route::get('/', function () {
            $user = auth()->user();
            // Кешируем список устройств на 2 секунды для быстрого обновления
            $cacheKey = 'devices_list_'.$user->id;
            $devices = null;

            // Получаем доступные ноды для пользователя
            $accessibleNodeIds = \App\Helpers\ZoneAccessHelper::getAccessibleNodeIds($user);

            // Пытаемся использовать теги, если поддерживаются
            try {
                $devices = \Illuminate\Support\Facades\Cache::tags(['devices_list'])->remember($cacheKey, 2, function () use ($user, $accessibleNodeIds) {
                    $query = DeviceNode::query()
                        ->select(['id', 'uid', 'zone_id', 'name', 'type', 'status', 'fw_version', 'last_seen_at'])
                        ->with('zone:id,name');

                    // Фильтруем по доступным нодам (кроме админов)
                    if (! $user->isAdmin()) {
                        $query->whereIn('id', $accessibleNodeIds);
                    }

                    return $query->latest('id') // Сортируем по ID, чтобы новые ноды были сверху
                        ->get();
                });
            } catch (\BadMethodCallException $e) {
                // Если теги не поддерживаются, используем обычный кеш
                $devices = \Illuminate\Support\Facades\Cache::remember($cacheKey, 2, function () use ($user, $accessibleNodeIds) {
                    $query = DeviceNode::query()
                        ->select(['id', 'uid', 'zone_id', 'name', 'type', 'status', 'fw_version', 'last_seen_at'])
                        ->with('zone:id,name');

                    // Фильтруем по доступным нодам (кроме админов)
                    if (! $user->isAdmin()) {
                        $query->whereIn('id', $accessibleNodeIds);
                    }

                    return $query->latest('id') // Сортируем по ID, чтобы новые ноды были сверху
                        ->get();
                });
            }

            return Inertia::render('Devices/Index', [
                'auth' => ['user' => ['role' => auth()->user()->role ?? 'viewer']],
                'devices' => $devices,
            ]);
        })->name('devices.index');

        /**
         * Devices Add - форма добавления устройства
         *
         * Inertia Props:
         * - auth: { user: { role: 'viewer'|'operator'|'admin' } }
         */
        Route::get('/add', function () {
            return Inertia::render('Devices/Add', [
                'auth' => ['user' => ['role' => auth()->user()->role ?? 'viewer']],
            ]);
        })->name('devices.add');

        /**
         * Device Show - детальная страница устройства
         *
         * Inertia Props:
         * - auth: { user: { role: 'viewer'|'operator'|'admin' } }
         * - device: {
         *     id: int,
         *     uid: string,
         *     zone_id: int,
         *     name: string,
         *     type: string,
         *     status: string,
         *     fw_version: string,
         *     last_seen_at: datetime,
         *     zone: { id: int, name: string },
         *     channels: Array<{ id, node_id, channel, type, metric, unit }>
         *   }
         *
         * Поддержка поиска по ID (int) или UID (string)
         */
        Route::get('/{nodeId}', function (string $nodeId) {
            // Support both ID (int) and UID (string) lookup
            $query = DeviceNode::query()
                ->with(['channels:id,node_id,channel,type,metric,unit', 'zone:id,name']);

            // Try to find by ID if nodeId is numeric, otherwise by UID
            if (is_numeric($nodeId)) {
                $device = $query->findOrFail((int) $nodeId);
            } else {
                $device = $query->where('uid', $nodeId)->firstOrFail();
            }

            return Inertia::render('Devices/Show', [
                'auth' => ['user' => ['role' => auth()->user()->role ?? 'viewer']],
                'device' => $device,
            ]);
        })->name('devices.show');
    });

    /**
     * Recipes routes
     */
    Route::prefix('recipes')->group(function () {
        Route::get('/create', function () {
            return Inertia::render('Recipes/Edit', [
                'auth' => ['user' => ['role' => auth()->user()->role ?? 'viewer']],
                'recipe' => null,
            ]);
        })->name('recipes.create');

        /**
         * Recipes Index - список всех рецептов
         *
         * Inertia Props:
         * - auth: { user: { role: 'viewer'|'operator'|'admin' } }
         * - recipes: Array<{
         *     id: int,
         *     name: string,
         *     description: string,
         *     phases_count: int
         *   }>
         *
         * Кеширование: 10 секунд
         */
        Route::get('/', function () {
            // Кешируем список рецептов на 10 секунд
            $cacheKey = 'recipes_list_'.auth()->id();
            $recipes = \Illuminate\Support\Facades\Cache::remember($cacheKey, 10, function () {
                return Recipe::query()
                    ->select(['id', 'name', 'description'])
                    ->with(['revisions.phases'])
                    ->get()
                    ->map(function ($recipe) {
                        // Подсчитываем общее количество фаз во всех ревизиях рецепта
                        $phasesCount = $recipe->revisions->sum(function ($revision) {
                            return $revision->phases->count();
                        });

                        return [
                            'id' => $recipe->id,
                            'name' => $recipe->name,
                            'description' => $recipe->description,
                            'phases_count' => $phasesCount,
                        ];
                    });
            });

            return Inertia::render('Recipes/Index', [
                'auth' => ['user' => ['role' => auth()->user()->role ?? 'viewer']],
                'recipes' => $recipes,
            ]);
        })->name('recipes.index');

        /**
         * Recipe Show - детальная страница рецепта
         *
         * Inertia Props:
         * - auth: { user: { role: 'viewer'|'operator'|'admin' } }
         * - recipe: {
         *     id: int,
         *     name: string,
         *     description: string,
         *     phases: Array<{ id, recipe_id, phase_index, name, duration_hours, targets }>
         *   }
         */
        Route::get('/{recipeId}', function (int $recipeId) {
            $recipe = Recipe::query()
                ->with(['latestPublishedRevision.phases'])
                ->findOrFail($recipeId);

            // Для совместимости с фронтендом добавляем phases на уровень recipe
            $recipeArray = $recipe->toArray();
            $recipeArray['phases'] = $recipe->latestPublishedRevision?->phases?->toArray() ?? [];
            $recipeArray['published_revision_id'] = $recipe->latestPublishedRevision?->id;

            return Inertia::render('Recipes/Show', [
                'auth' => ['user' => ['role' => auth()->user()->role ?? 'viewer']],
                'recipe' => $recipeArray,
            ]);
        })->name('recipes.show');

        /**
         * Recipe Edit - форма редактирования рецепта
         *
         * Inertia Props:
         * - auth: { user: { role: 'viewer'|'operator'|'admin' } }
         * - recipe: {
         *     id: int,
         *     name: string,
         *     description: string,
         *     phases: Array<{ id, recipe_id, phase_index, name, duration_hours, targets }>
         *   }
         */
        Route::get('/create', function () {
            $recipe = new \App\Models\Recipe;
            $recipe->phases = [];

            return Inertia::render('Recipes/Edit', [
                'recipe' => $recipe,
            ]);
        })->name('recipes.create');

        Route::get('/{recipeId}/edit', function (int $recipeId) {
            $recipe = Recipe::query()
                ->with(['latestDraftRevision.phases', 'latestPublishedRevision'])
                ->findOrFail($recipeId);

            // Для совместимости с фронтендом добавляем phases на уровень recipe
            $phases = $recipe->latestDraftRevision?->phases
                ?? $recipe->latestPublishedRevision?->phases
                ?? collect();
            $recipeArray = $recipe->toArray();
            $recipeArray['phases'] = $phases->toArray();
            $recipeArray['draft_revision_id'] = $recipe->latestDraftRevision?->id;
            $recipeArray['published_revision_id'] = $recipe->latestPublishedRevision?->id;

            return Inertia::render('Recipes/Edit', [
                'auth' => ['user' => ['role' => auth()->user()->role ?? 'viewer']],
                'recipe' => $recipeArray,
            ]);
        })->name('recipes.edit');
    });

    /**
     * Alerts Index - список всех алертов
     *
     * Inertia Props:
     * - auth: { user: { role: 'viewer'|'operator'|'admin' } }
     * - alerts: Array<{
     *     id: int,
     *     type: string,
     *     status: 'active'|'resolved',
     *     details: object,
     *     zone_id: int,
     *     created_at: datetime,
     *     resolved_at: datetime|null,
     *     zone: { id: int, name: string }
     *   }>
     *
     * Кеширование: 5 секунд (более динамичные данные)
     */
    Route::get('/alerts', function () {
        // Кешируем список алертов на 5 секунд (более динамичные данные)
        $cacheKey = 'alerts_list_'.auth()->id();
        $alerts = \Illuminate\Support\Facades\Cache::remember($cacheKey, 5, function () {
            return \App\Models\Alert::query()
                ->with(['zone' => function ($q) {
                    $q->select('id', 'name');
                }])
                ->latest('id')
                ->limit(100)
                ->get(['id', 'type', 'status', 'details', 'zone_id', 'created_at', 'resolved_at']);
        });

        return Inertia::render('Alerts/Index', [
            'auth' => ['user' => ['role' => auth()->user()->role ?? 'viewer']],
            'alerts' => $alerts,
        ]);
    })->name('alerts.index');

    /**
     * Users Index - страница управления пользователями (только для admin)
     *
     * Inertia Props:
     * - auth: {
     *     user: {
     *       id: int,
     *       name: string,
     *       email: string,
     *       role: 'admin'
     *     }
     *   }
     * - users: Array<{ id, name, email, role, created_at }>
     */
    Route::middleware('role:admin')->get('/users', function () {
        $user = auth()->user();
        $users = \App\Models\User::query()
            ->select(['id', 'name', 'email', 'role', 'created_at'])
            ->orderBy('id')
            ->get();

        return Inertia::render('Users/Index', [
            'auth' => [
                'user' => [
                    'id' => $user->id,
                    'name' => $user->name,
                    'email' => $user->email,
                    'role' => $user->role ?? 'viewer',
                ],
            ],
            'users' => $users,
        ]);
    })->name('users.index');

    /**
     * Audit Index - страница аудита (только для admin)
     *
     * Inertia Props:
     * - auth: {
     *     user: {
     *       id: int,
     *       name: string,
     *       email: string,
     *       role: 'admin'
     *     }
     *   }
     * - logs: Array<{ id, level, message, context, created_at }>
     *
     * Кеширование: 5 секунд (динамичные данные)
     */
    Route::middleware('role:admin')->get('/audit', function () {
        $user = auth()->user();

        // Кешируем логи на 5 секунд для снижения нагрузки
        $cacheKey = 'audit_logs_'.auth()->id();
        $logs = \Illuminate\Support\Facades\Cache::remember($cacheKey, 5, function () {
            try {
                $result = \App\Models\SystemLog::query()
                    ->select(['id', 'level', 'message', 'context', 'created_at'])
                    ->orderBy('created_at', 'desc')
                    ->limit(1000)
                    ->get();

                // Логируем для отладки
                \Log::info('Audit logs loaded', ['count' => $result->count()]);

                return $result;
            } catch (\Exception $e) {
                \Log::error('Failed to load audit logs', ['error' => $e->getMessage()]);

                return collect([]);
            }
        });

        return Inertia::render('Audit/Index', [
            'auth' => [
                'user' => [
                    'id' => $user->id,
                    'name' => $user->name,
                    'email' => $user->email,
                    'role' => $user->role ?? 'viewer',
                ],
            ],
            'logs' => $logs,
        ]);
    })->name('audit.index');

    /**
     * Logs Index - страница логов сервисов (admin/operator/engineer)
     */
    Route::middleware('role:admin,operator,engineer')->get('/logs', function (Request $request) {
        $serviceCatalog = [
            'automation-engine' => [
                'label' => 'Automation Engine',
                'description' => 'События ядра автоматики и командные переходы.',
            ],
            'system' => [
                'label' => 'System Services',
                'description' => 'Системные сервисы, очередь, запуск крон-заданий.',
            ],
        ];

        $levelFilter = $request->query('level');
        $serviceFilter = $request->query('service');
        if ($serviceFilter === 'all') {
            $serviceFilter = null;
        }

        $logsByService = collect($serviceCatalog)
            ->map(function ($meta, $serviceKey) use ($levelFilter) {
                $query = SystemLog::query()
                    ->select(['id', 'level', 'message', 'context', 'created_at'])
                    ->orderBy('created_at', 'desc')
                    ->when($serviceKey, fn ($q) => $q->where('context->service', $serviceKey));

                if ($levelFilter) {
                    $query->whereRaw('UPPER(level) = ?', [strtoupper($levelFilter)]);
                }

                return [
                    'key' => $serviceKey,
                    'label' => $meta['label'],
                    'description' => $meta['description'],
                    'entries' => $query->limit(75)->get()->map(function ($log) {
                        return [
                            'id' => $log->id,
                            'level' => strtoupper($log->level ?? 'info'),
                            'message' => $log->message,
                            'context' => $log->context ?? [],
                            'created_at' => (string) $log->created_at,
                        ];
                    }),
                ];
            })
            ->filter(fn ($item) => ! $serviceFilter || $item['key'] === $serviceFilter)
            ->values()
            ->toArray();

        $levelFilters = collect($logsByService)
            ->flatMap(fn ($service) => collect($service['entries'])->pluck('level'))
            ->unique()
            ->values()
            ->toArray();

        $serviceOptions = collect($serviceCatalog)
            ->map(fn ($meta, $key) => ['key' => $key, 'label' => $meta['label']])
            ->values()
            ->toArray();

        return Inertia::render('Logs/Index', [
            'auth' => ['user' => ['role' => auth()->user()->role ?? 'viewer']],
            'serviceLogs' => $logsByService,
            'serviceOptions' => $serviceOptions,
            'levelFilters' => $levelFilters,
            'selectedService' => $serviceFilter ?? 'all',
            'selectedLevel' => $levelFilter ?? '',
        ]);
    })->name('logs.index');

    /**
     * Settings Index - страница настроек
     *
     * Inertia Props:
     * - auth: {
     *     user: {
     *       id: int,
     *       name: string,
     *       email: string,
     *       role: 'viewer'|'operator'|'admin'
     *     }
     *   }
     * - users: Array<{ id, name, email, role, created_at }> - только для admin
     */
    Route::get('/settings', function () {
        $user = auth()->user();
        $users = [];

        // Загрузить пользователей только для админов
        if ($user->role === 'admin') {
            $users = \App\Models\User::query()
                ->select(['id', 'name', 'email', 'role', 'created_at'])
                ->orderBy('id')
                ->get();
        }

        return Inertia::render('Settings/Index', [
            'auth' => [
                'user' => [
                    'id' => $user->id,
                    'name' => $user->name,
                    'email' => $user->email,
                    'role' => $user->role ?? 'viewer',
                ],
            ],
            'users' => $users,
        ]);
    })->name('settings.index');

    // User management routes (admin only, using web session auth)
    Route::middleware('role:admin')->prefix('settings/users')->group(function () {
        Route::post('/', function (\Illuminate\Http\Request $request) {
            $data = $request->validate([
                'name' => ['required', 'string', 'max:255'],
                'email' => ['required', 'string', 'email', 'max:255', 'unique:users,email'],
                'password' => ['required', 'string', 'min:8'],
                'role' => ['required', 'string', 'in:admin,operator,viewer'],
            ]);

            $user = \App\Models\User::create([
                'name' => $data['name'],
                'email' => $data['email'],
                'password' => \Illuminate\Support\Facades\Hash::make($data['password']),
                'role' => $data['role'],
            ]);

            return redirect()->route('users.index');
        })->name('settings.users.store');

        Route::patch('/{id}', function (\Illuminate\Http\Request $request, int $id) {
            $user = \App\Models\User::findOrFail($id);

            $data = $request->validate([
                'name' => ['required', 'string', 'max:255'],
                'email' => ['required', 'string', 'email', 'max:255', 'unique:users,email,'.$id],
                'password' => ['nullable', 'string', 'min:8'],
                'role' => ['required', 'string', 'in:admin,operator,viewer'],
            ]);

            $user->name = $data['name'];
            $user->email = $data['email'];
            $user->role = $data['role'];
            if (! empty($data['password'])) {
                $user->password = \Illuminate\Support\Facades\Hash::make($data['password']);
            }
            $user->save();

            return redirect()->route('users.index');
        })->name('settings.users.update');

        Route::delete('/{id}', function (int $id) {
            $user = \App\Models\User::findOrFail($id);
            // Нельзя удалить самого себя
            if ($user->id === auth()->id()) {
                return redirect()->route('users.index')->withErrors(['error' => 'Нельзя удалить самого себя']);
            }
            $user->delete();

            return redirect()->route('users.index');
        })->name('settings.users.destroy');
    });

    /**
     * Admin routes (только для admin)
     */
    Route::middleware('role:admin')->prefix('admin')->group(function () {
        /**
         * Admin Index - главная страница админки
         *
         * Inertia Props:
         * - auth: { user: { role: 'admin' } }
         */
        Route::get('/', fn () => Inertia::render('Admin/Index', [
            'auth' => ['user' => ['role' => auth()->user()->role ?? 'viewer']],
        ]))->name('admin.index');

        /**
         * Admin Zones - управление зонами
         *
         * Inertia Props:
         * - auth: { user: { role: 'admin' } }
         * - zones: Array<{ id, name, status, description, greenhouse_id, greenhouse }>
         */
        Route::get('/zones', function () {
            $zones = Zone::query()
                ->select(['id', 'name', 'status', 'description', 'greenhouse_id'])
                ->with('greenhouse:id,name')
                ->get();

            return Inertia::render('Admin/Zones', [
                'auth' => ['user' => ['role' => auth()->user()->role ?? 'viewer']],
                'zones' => $zones,
            ]);
        })->name('admin.zones');

        /**
         * Admin Recipes - управление рецептами
         *
         * Inertia Props:
         * - auth: { user: { role: 'admin' } }
         * - recipes: Array<{ id, name, description, phases_count }>
         */
        Route::get('/recipes', function () {
            $recipes = Recipe::query()
                ->select(['id', 'name', 'description'])
                ->with(['revisions.phases'])
                ->get()
                ->map(function (Recipe $recipe) {
                    $phasesCount = $recipe->revisions->sum(function ($revision) {
                        return $revision->phases->count();
                    });

                    return [
                        'id' => $recipe->id,
                        'name' => $recipe->name,
                        'description' => $recipe->description,
                        'phases_count' => $phasesCount,
                    ];
                });

            return Inertia::render('Admin/Recipes', [
                'auth' => ['user' => ['role' => auth()->user()->role ?? 'viewer']],
                'recipes' => $recipes,
            ]);
        })->name('admin.recipes');
    });
});

// Swagger доступен только для авторизованных пользователей в dev/testing окружениях
// В production должен быть отключен или защищен дополнительной аутентификацией
Route::get('/swagger', function () {
    if (app()->environment(['production', 'staging'])) {
        abort(404, 'Swagger documentation is not available in this environment');
    }
    if (! auth()->check()) {
        return redirect()->route('login');
    }

    return redirect('/swagger.html');
})->middleware('auth');

Route::middleware(['web', 'auth', 'role:admin,operator,agronomist'])->group(function () {
    Route::get('/plants', [PlantController::class, 'index'])->name('plants.index');
    Route::get('/plants/{plant}', [PlantController::class, 'show'])->name('plants.show');
    Route::post('/plants', [PlantController::class, 'store'])->name('plants.store');
    Route::put('/plants/{plant}', [PlantController::class, 'update'])->name('plants.update');
    Route::delete('/plants/{plant}', [PlantController::class, 'destroy'])->name('plants.destroy');
    Route::post('/plants/{plant}/prices', [PlantController::class, 'storePriceVersion'])->name('plants.prices.store');
});

Route::middleware(['web', 'auth'])->group(function () {
    Route::get('/profile', [ProfileController::class, 'edit'])->name('profile.edit');
    Route::patch('/profile', [ProfileController::class, 'update'])->name('profile.update');
    Route::delete('/profile', [ProfileController::class, 'destroy'])->name('profile.destroy');

    /**
     * Monitoring - страница мониторинга системы
     *
     * Inertia Props:
     * - auth: { user: { role: string } }
     */
    Route::get('/monitoring', fn () => Inertia::render('Monitoring/Index', [
        'auth' => ['user' => ['role' => auth()->user()->role ?? 'viewer']],
    ]))->name('monitoring.index');
});

require __DIR__.'/auth.php';

// Тестовый backdoor доступен ТОЛЬКО в testing окружении (не в local!)
// Это предотвращает случайное включение в production при ошибочной конфигурации env
if (app()->environment('testing')) {
    Route::get('/testing/login/{user}', function (\App\Models\User $user) {
        \Illuminate\Support\Facades\Auth::login($user);
        \Log::warning('Testing backdoor used', [
            'user_id' => $user->id,
            'ip' => request()->ip(),
        ]);

        return redirect()->intended('/');
    })->name('testing.login');
}
