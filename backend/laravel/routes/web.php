<?php

use Illuminate\Support\Facades\Route;
use Inertia\Inertia;
use App\Models\Zone;
use App\Models\DeviceNode;
use App\Models\NodeChannel;
use App\Models\Recipe;
use App\Models\Alert;
use App\Models\Greenhouse;

Route::middleware(['web', 'auth', 'role:viewer,operator,admin'])->group(function () {
    Route::get('/', function () {
        // Используем кеш для статических данных (TTL 30 секунд)
        $cacheKey = 'dashboard_data_' . auth()->id();
        $dashboard = \Illuminate\Support\Facades\Cache::remember($cacheKey, 30, function () {
            // Оптимизированные запросы - выполняем все параллельно через DB::select
            $stats = \Illuminate\Support\Facades\DB::select("
                SELECT 
                    (SELECT COUNT(*) FROM greenhouses) as greenhouses_count,
                    (SELECT COUNT(*) FROM zones) as zones_count,
                    (SELECT COUNT(*) FROM nodes) as devices_count,
                    (SELECT COUNT(*) FROM alerts WHERE status = 'active') as alerts_count
            ")[0];
            
            // Статистика по статусам зон и узлов одним запросом
            $zonesByStatus = Zone::query()
                ->selectRaw('status, COUNT(*) as count')
                ->groupBy('status')
                ->pluck('count', 'status')
                ->toArray();
            
            $nodesByStatus = DeviceNode::query()
                ->selectRaw('status, COUNT(*) as count')
                ->groupBy('status')
                ->pluck('count', 'status')
                ->toArray();
            
            // Оптимизированный запрос проблемных зон - используем JOIN вместо whereHas
            $problematicZones = Zone::query()
                ->select(['zones.id', 'zones.name', 'zones.status', 'zones.description', 'zones.greenhouse_id'])
                ->leftJoin('alerts', function ($join) {
                    $join->on('alerts.zone_id', '=', 'zones.id')
                         ->where('alerts.status', '=', 'active');
                })
                ->where(function ($q) {
                    $q->whereIn('zones.status', ['ALARM', 'WARNING'])
                      ->orWhereNotNull('alerts.id');
                })
                ->selectRaw('COUNT(DISTINCT alerts.id) as alerts_count')
                ->groupBy('zones.id', 'zones.name', 'zones.status', 'zones.description', 'zones.greenhouse_id')
                ->orderByRaw("CASE zones.status WHEN 'ALARM' THEN 1 WHEN 'WARNING' THEN 2 ELSE 3 END")
                ->orderBy('alerts_count', 'desc')
                ->limit(5)
                ->with('greenhouse:id,name')
                ->get();
            
            // Теплицы с оптимизированным подсчетом
            $greenhouses = Greenhouse::query()
                ->select(['id', 'uid', 'name', 'type'])
                ->withCount(['zones', 'zones as zones_running' => function ($q) {
                    $q->where('status', 'RUNNING');
                }])
                ->get();
            
            // Последние алерты
            $latestAlerts = Alert::query()
                ->select(['id', 'type', 'status', 'details', 'zone_id', 'created_at'])
                ->with('zone:id,name')
                ->where('status', 'active')
                ->latest('id')
                ->limit(10)
                ->get();
            
            return [
                'greenhousesCount' => (int)$stats->greenhouses_count,
                'zonesCount' => (int)$stats->zones_count,
                'devicesCount' => (int)$stats->devices_count,
                'alertsCount' => (int)$stats->alerts_count,
                'zonesByStatus' => $zonesByStatus,
                'nodesByStatus' => $nodesByStatus,
                'problematicZones' => $problematicZones,
                'greenhouses' => $greenhouses,
                'latestAlerts' => $latestAlerts,
            ];
        });
        
        return Inertia::render('Dashboard/Index', [
            'auth' => ['user' => ['role' => auth()->user()->role ?? 'viewer']],
            'dashboard' => $dashboard,
        ]);
    })->name('dashboard');

    Route::prefix('zones')->group(function () {
        Route::get('/', function () {
            // Кешируем список зон на 10 секунд
            $cacheKey = 'zones_list_' . auth()->id();
            $zones = \Illuminate\Support\Facades\Cache::remember($cacheKey, 10, function () {
                return Zone::query()
                    ->select(['id','name','status','description','greenhouse_id'])
                    ->with('greenhouse:id,name')
                    ->get();
            });
            
            // Загружаем telemetry для всех зон (batch loading)
            $zoneIds = $zones->pluck('id')->toArray();
            $telemetryByZone = [];
            
            if (!empty($zoneIds)) {
                $telemetryAll = \App\Models\TelemetryLast::query()
                    ->whereIn('zone_id', $zoneIds)
                    ->get(['zone_id', 'metric_type', 'value']);
                
                // Группируем по zone_id и преобразуем в формат {ph, ec, temperature, humidity}
                $telemetryByZone = $telemetryAll->groupBy('zone_id')->map(function ($metrics) {
                    $result = ['ph' => null, 'ec' => null, 'temperature' => null, 'humidity' => null];
                    foreach ($metrics as $metric) {
                        $key = strtolower($metric->metric_type ?? '');
                        if ($key === 'ph') $result['ph'] = $metric->value;
                        elseif ($key === 'ec') $result['ec'] = $metric->value;
                        elseif (in_array($key, ['temp_air', 'temp', 'temperature'])) $result['temperature'] = $metric->value;
                        elseif (in_array($key, ['humidity', 'rh'])) $result['humidity'] = $metric->value;
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
        Route::get('/{zoneId}', function (string $zoneId) {
            // Convert zoneId to integer
            $zoneIdInt = (int)$zoneId;
            
            $zone = Zone::query()
                ->select(['id','name','status','description','greenhouse_id'])
                ->with(['greenhouse:id,name', 'recipeInstance.recipe:id,name'])
                ->findOrFail($zoneIdInt);
            
            // Загрузить телеметрию
            $telemetryLast = \App\Models\TelemetryLast::query()
                ->where('zone_id', $zoneIdInt)
                ->get(['metric_type', 'value'])
                ->mapWithKeys(function ($item) {
                    $key = strtolower($item->metric_type ?? '');
                    if ($key === 'ph') return ['ph' => $item->value];
                    if ($key === 'ec') return ['ec' => $item->value];
                    if (in_array($key, ['temp_air', 'temp', 'temperature'])) return ['temperature' => $item->value];
                    if (in_array($key, ['humidity', 'rh'])) return ['humidity' => $item->value];
                    return [];
                })
                ->toArray();
            
            // Загрузить цели из текущей фазы рецепта
            $targets = [];
            if ($zone->recipeInstance?->recipe) {
                $currentPhaseIndex = $zone->recipeInstance->current_phase_index ?? 0;
                $zone->load(['recipeInstance.recipe.phases' => function ($q) use ($currentPhaseIndex) {
                    $q->where('phase_index', $currentPhaseIndex);
                }]);
                $currentPhase = $zone->recipeInstance->recipe->phases->first();
                if ($currentPhase && $currentPhase->targets) {
                    $targets = $currentPhase->targets;
                }
            }
            
            // Загрузить устройства зоны
            $devices = \App\Models\DeviceNode::query()
                ->select(['id','uid','zone_id','name','type','status','fw_version','last_seen_at'])
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
                        $message = $details['message'] ?? $details['msg'] ?? $event->type ?? '';
                        
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
            
            return Inertia::render('Zones/Show', [
                'auth' => ['user' => ['role' => auth()->user()->role ?? 'viewer']],
                'zoneId' => $zoneIdInt,
                'zone' => $zone,
                'telemetry' => $telemetryLast,
                'targets' => $targets,
                'devices' => $devices,
                'events' => $events,
                'cycles' => $cycles,
            ]);
        })->name('zones.show');
    });

    Route::prefix('devices')->group(function () {
        Route::get('/', function () {
            // Кешируем список устройств на 10 секунд
            $cacheKey = 'devices_list_' . auth()->id();
            $devices = \Illuminate\Support\Facades\Cache::remember($cacheKey, 10, function () {
                return DeviceNode::query()
                    ->select(['id','uid','zone_id','name','type','status','fw_version','last_seen_at'])
                    ->with('zone:id,name')
                    ->get();
            });
            return Inertia::render('Devices/Index', [
                'auth' => ['user' => ['role' => auth()->user()->role ?? 'viewer']],
                'devices' => $devices,
            ]);
        })->name('devices.index');
        Route::get('/add', function () {
            return Inertia::render('Devices/Add', [
                'auth' => ['user' => ['role' => auth()->user()->role ?? 'viewer']],
            ]);
        })->name('devices.add');
        Route::get('/{nodeId}', function (string $nodeId) {
            // Support both ID (int) and UID (string) lookup
            $query = DeviceNode::query()
                ->with(['channels:id,node_id,channel,type,metric,unit','zone:id,name']);
            
            // Try to find by ID if nodeId is numeric, otherwise by UID
            if (is_numeric($nodeId)) {
                $device = $query->findOrFail((int)$nodeId);
            } else {
                $device = $query->where('uid', $nodeId)->firstOrFail();
            }
            return Inertia::render('Devices/Show', [
                'auth' => ['user' => ['role' => auth()->user()->role ?? 'viewer']],
                'device' => $device,
            ]);
        })->name('devices.show');
    });

    Route::prefix('recipes')->group(function () {
        Route::get('/', function () {
            // Кешируем список рецептов на 10 секунд
            $cacheKey = 'recipes_list_' . auth()->id();
            $recipes = \Illuminate\Support\Facades\Cache::remember($cacheKey, 10, function () {
                return Recipe::query()
                    ->select(['id','name','description'])
                    ->withCount('phases')
                    ->get()
                    ->map(function ($recipe) {
                        return [
                            'id' => $recipe->id,
                            'name' => $recipe->name,
                            'description' => $recipe->description,
                            'phases_count' => $recipe->phases_count ?? 0,
                        ];
                    });
            });
            return Inertia::render('Recipes/Index', [
                'auth' => ['user' => ['role' => auth()->user()->role ?? 'viewer']],
                'recipes' => $recipes,
            ]);
        })->name('recipes.index');
        Route::get('/{recipeId}', function (int $recipeId) {
            $recipe = Recipe::query()
                ->with('phases:id,recipe_id,phase_index,name,duration_hours,targets')
                ->findOrFail($recipeId);
            return Inertia::render('Recipes/Show', [
                'auth' => ['user' => ['role' => auth()->user()->role ?? 'viewer']],
                'recipe' => $recipe,
            ]);
        })->name('recipes.show');
        Route::get('/{recipeId}/edit', function (int $recipeId) {
            $recipe = Recipe::query()
                ->with('phases:id,recipe_id,phase_index,name,duration_hours,targets')
                ->findOrFail($recipeId);
            return Inertia::render('Recipes/Edit', [
                'auth' => ['user' => ['role' => auth()->user()->role ?? 'viewer']],
                'recipe' => $recipe,
            ]);
        })->name('recipes.edit');
    });

        Route::get('/alerts', function () {
            // Кешируем список алертов на 5 секунд (более динамичные данные)
            $cacheKey = 'alerts_list_' . auth()->id();
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
            
            return redirect()->route('settings.index');
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
            if (!empty($data['password'])) {
                $user->password = \Illuminate\Support\Facades\Hash::make($data['password']);
            }
            $user->save();
            
            return redirect()->route('settings.index');
        })->name('settings.users.update');
        
        Route::delete('/{id}', function (int $id) {
            $user = \App\Models\User::findOrFail($id);
            // Нельзя удалить самого себя
            if ($user->id === auth()->id()) {
                return redirect()->route('settings.index')->withErrors(['error' => 'Нельзя удалить самого себя']);
            }
            $user->delete();
            return redirect()->route('settings.index');
        })->name('settings.users.destroy');
    });

    // Admin
    Route::middleware('role:admin')->prefix('admin')->group(function () {
        Route::get('/', fn () => Inertia::render('Admin/Index', [
            'auth' => ['user' => ['role' => auth()->user()->role ?? 'viewer']],
        ]))->name('admin.index');
        Route::get('/zones', function () {
            $zones = Zone::query()
                ->select(['id','name','status','description','greenhouse_id'])
                ->with('greenhouse:id,name')
                ->get();
            return Inertia::render('Admin/Zones', [
                'auth' => ['user' => ['role' => auth()->user()->role ?? 'viewer']],
                'zones' => $zones,
            ]);
        })->name('admin.zones');
        Route::get('/recipes', function () {
            $recipes = Recipe::query()
                ->select(['id','name','description'])
                ->withCount('phases')
                ->get();
            return Inertia::render('Admin/Recipes', [
                'auth' => ['user' => ['role' => auth()->user()->role ?? 'viewer']],
                'recipes' => $recipes,
            ]);
        })->name('admin.recipes');
    });
});

Route::get('/swagger', function () {
    return redirect('/swagger.html');
});

require __DIR__.'/auth.php';
