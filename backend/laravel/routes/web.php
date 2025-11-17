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
        // Статистика по статусам зон
        $zonesByStatus = Zone::query()
            ->selectRaw('status, COUNT(*) as count')
            ->groupBy('status')
            ->pluck('count', 'status')
            ->toArray();
        
        // Статистика по статусам узлов
        $nodesByStatus = DeviceNode::query()
            ->selectRaw('status, COUNT(*) as count')
            ->groupBy('status')
            ->pluck('count', 'status')
            ->toArray();
        
        // Проблемные зоны (ALARM, WARNING или с активными алертами)
        $problematicZones = Zone::query()
            ->withCount(['alerts' => function ($q) {
                $q->where('status', 'active');
            }])
            ->where(function ($q) {
                $q->whereIn('status', ['ALARM', 'WARNING'])
                  ->orWhereHas('alerts', function ($q2) {
                      $q2->where('status', 'active');
                  });
            })
            ->orderByRaw("CASE status WHEN 'ALARM' THEN 1 WHEN 'WARNING' THEN 2 ELSE 3 END")
            ->orderBy('alerts_count', 'desc')
            ->limit(5)
            ->get(['id', 'name', 'status', 'description', 'greenhouse_id'])
            ->load('greenhouse:id,name');
        
        // Теплицы с краткой информацией
        $greenhouses = Greenhouse::query()
            ->withCount(['zones', 'zones as zones_running' => function ($q) {
                $q->where('status', 'RUNNING');
            }])
            ->get(['id', 'uid', 'name', 'type']);
        
        $dashboard = [
            'greenhousesCount' => Greenhouse::query()->count(),
            'zonesCount' => Zone::query()->count(),
            'devicesCount' => DeviceNode::query()->count(),
            'alertsCount' => Alert::query()->where('status', 'active')->count(),
            'zonesByStatus' => $zonesByStatus,
            'nodesByStatus' => $nodesByStatus,
            'problematicZones' => $problematicZones,
            'greenhouses' => $greenhouses,
            'latestAlerts' => Alert::query()
                ->with(['zone' => function ($q) {
                    $q->select('id', 'name');
                }])
                ->latest('id')
                ->limit(10)
                ->get(['id', 'type', 'status', 'details', 'zone_id', 'created_at']),
        ];
        return Inertia::render('Dashboard/Index', [
            'auth' => ['user' => ['role' => auth()->user()->role ?? 'viewer']],
            'dashboard' => $dashboard,
        ]);
    })->name('dashboard');

    Route::prefix('zones')->group(function () {
        Route::get('/', function () {
            $zones = Zone::query()
                ->select(['id','name','status','description','greenhouse_id'])
                ->with('greenhouse:id,name')
                ->get();
            return Inertia::render('Zones/Index', [
                'auth' => ['user' => ['role' => auth()->user()->role ?? 'viewer']],
                'zones' => $zones,
            ]);
        })->name('zones.web.index');
        Route::get('/{zoneId}', function (string $zoneId) {
            $zone = Zone::query()
                ->select(['id','name','status','description','greenhouse_id'])
                ->with(['greenhouse:id,name', 'recipeInstance.recipe:id,name'])
                ->findOrFail($zoneId);
            
            // Загрузить телеметрию
            $telemetryLast = \App\Models\TelemetryLast::query()
                ->where('zone_id', $zoneId)
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
                ->where('zone_id', $zoneId)
                ->with('zone:id,name')
                ->get();
            
            // Загрузить последние события зоны
            $events = \App\Models\Event::query()
                ->where('zone_id', $zoneId)
                ->select(['id', 'kind', 'message', 'occurred_at'])
                ->latest('occurred_at')
                ->limit(20)
                ->get();
            
            return Inertia::render('Zones/Show', [
                'auth' => ['user' => ['role' => auth()->user()->role ?? 'viewer']],
                'zoneId' => (int)$zoneId,
                'zone' => $zone,
                'telemetry' => $telemetryLast,
                'targets' => $targets,
                'devices' => $devices,
                'events' => $events,
            ]);
        })->name('zones.show');
    });

    Route::prefix('devices')->group(function () {
        Route::get('/', function () {
            $devices = DeviceNode::query()
                ->select(['id','uid','zone_id','name','type','status','fw_version','last_seen_at'])
                ->with('zone:id,name')
                ->get();
            return Inertia::render('Devices/Index', [
                'auth' => ['user' => ['role' => auth()->user()->role ?? 'viewer']],
                'devices' => $devices,
            ]);
        })->name('devices.index');
        Route::get('/{nodeId}', function (int $nodeId) {
            $device = DeviceNode::query()
                ->with(['channels:id,node_id,channel,type,metric,unit','zone:id,name'])
                ->findOrFail($nodeId);
            return Inertia::render('Devices/Show', [
                'auth' => ['user' => ['role' => auth()->user()->role ?? 'viewer']],
                'device' => $device,
            ]);
        })->name('devices.show');
    });

    Route::prefix('recipes')->group(function () {
        Route::get('/', function () {
            $recipes = Recipe::query()
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
            $alerts = \App\Models\Alert::query()
                ->with(['zone' => function ($q) {
                    $q->select('id', 'name');
                }])
                ->latest('id')
                ->limit(100)
                ->get(['id', 'type', 'status', 'details', 'zone_id', 'created_at', 'resolved_at']);
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
