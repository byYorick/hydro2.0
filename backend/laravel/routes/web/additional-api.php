<?php

/*
|--------------------------------------------------------------------------
| Additional API Routes
|--------------------------------------------------------------------------
|
| Дополнительные API маршруты для устройств, рецептов, пользователей.
|
*/

use Illuminate\Support\Facades\Route;

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
                ->with(['channels:id,node_id,channel,type,metric,unit,config', 'zone:id,name']);

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
                ->with(['latestDraftRevision.phases'])
                ->findOrFail($recipeId);

            // Для совместимости с фронтендом добавляем phases на уровень recipe
            $recipeArray = $recipe->toArray();
            $recipeArray['phases'] = $recipe->latestDraftRevision?->phases?->toArray() ?? [];

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
            'history-logger' => [
                'label' => 'History Logger',
                'description' => 'Архив событий телеметрии и подтверждений команд.',
            ],
            'scheduler' => [
                'label' => 'Scheduler',
                'description' => 'Запуск расписаний полива, освещения и заданий.',
            ],
            'mqtt-bridge' => [
                'label' => 'MQTT Bridge',
                'description' => 'REST→MQTT мост и публикация команд.',
            ],
            'laravel' => [
                'label' => 'Laravel',
                'description' => 'Веб-приложение, фоновые задачи и WebSocket.',
            ],
            'system' => [
                'label' => 'System',
                'description' => 'Общие события: очередь, cron, миграции.',
            ],
        ];

        $serviceOptions = collect($serviceCatalog)
            ->map(fn ($meta, $key) => ['key' => $key, 'label' => $meta['label'], 'description' => $meta['description']])
            ->values()
            ->toArray();

        return Inertia::render('Logs/Index', [
            'auth' => ['user' => ['role' => auth()->user()->role ?? 'viewer']],
            'serviceOptions' => $serviceOptions,
            'defaultService' => $request->query('service', 'all'),
            'defaultLevel' => $request->query('level', ''),
            'defaultSearch' => $request->query('search', ''),
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
                ->withCount('phases')
                ->get();

            return Inertia::render('Admin/Recipes', [
                'auth' => ['user' => ['role' => auth()->user()->role ?? 'viewer']],
                'recipes' => $recipes,
            ]);
        })->name('admin.recipes');
    });
});

