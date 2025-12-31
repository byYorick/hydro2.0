<?php

/*
|--------------------------------------------------------------------------
| Zones API Routes
|--------------------------------------------------------------------------
|
| API маршруты для получения детальной информации о зонах.
| Включает телеметрию, активные циклы, устройства и события.
|
*/

use Illuminate\Support\Facades\Route;

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
                        'activeGrowCycle.currentPhase',
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
                        'telemetry_last.last_value as value'
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
                    'activeGrowCycle.currentPhase',
                    'activeGrowCycle.plant:id,name',
                ])
                ->findOrFail($zoneIdInt);

            // Обновляем зону, чтобы гарантировать загрузку свежих данных
            $zone->refresh();
            $zone->loadMissing([
                'activeGrowCycle.recipeRevision.recipe',
                'activeGrowCycle.currentPhase',
                'activeGrowCycle.plant',
            ]);

            // Загрузить телеметрию
            $telemetryLast = \App\Models\TelemetryLast::query()
                ->join('sensors', 'telemetry_last.sensor_id', '=', 'sensors.id')
                ->where('sensors.zone_id', $zoneIdInt)
                ->whereNotNull('sensors.zone_id')
                ->select([
                    'sensors.type as metric_type',
                    'telemetry_last.last_value as value'
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

            // Загрузить цели из активного цикла выращивания (новая модель)
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
            
            // Если нет активного цикла и эффективных targets - targets остаются пустыми

            // Нормализованный блок current_phase с UTC-таймингами и агрегированными таргетами
            // Используем activeGrowCycle (новая модель) вместо recipeInstance
            $currentPhaseNormalized = null;
            if ($activeGrowCycle && $activeGrowCycle->currentPhase) {
                try {
                    $effectiveTargetsService = app(\App\Services\EffectiveTargetsService::class);
                    $effectiveTargets = $effectiveTargetsService->getEffectiveTargets($activeGrowCycle->id);
                    $phase = $effectiveTargets['phase'] ?? null;
                    $effectiveTargetsData = $effectiveTargets['targets'] ?? [];
                    
                    if ($phase) {
                        $currentPhaseNormalized = [
                            'index' => $activeGrowCycle->currentPhase->phase_index ?? 0,
                            'name' => $phase['name'] ?? $phase['code'] ?? "Фаза " . ($activeGrowCycle->currentPhase->phase_index ?? 0),
                            'duration_hours' => $activeGrowCycle->currentPhase->duration_hours ?? ($activeGrowCycle->currentPhase->duration_days * 24 ?? 0),
                            'phase_started_at' => $activeGrowCycle->phase_started_at?->toIso8601String() ?? $phase['started_at'],
                            'phase_ends_at' => $phase['due_at'] ?? null,
                            'targets' => $effectiveTargetsData,
                        ];
                    }
                } catch (\Exception $e) {
                    \Log::warning('Failed to get effective targets for current phase', [
                        'zone_id' => $zone->id,
                        'cycle_id' => $activeGrowCycle->id,
                        'error' => $e->getMessage(),
                    ]);
                }
            }
            
            // Legacy fallback удален - используем только новую модель activeGrowCycle

            // Агрегированный цикл выращивания (один активный на зону).
            $activeCycleModel = \App\Models\GrowCycle::query()
                ->where('zone_id', $zone->id)
                ->whereIn('status', ['PLANNED', 'RUNNING', 'PAUSED'])
                ->latest('started_at')
                ->first();

            $activeCycle = null;
            if ($activeCycleModel) {
                $activeCycle = [
                    'id' => $activeCycleModel->id,
                    'type' => 'GROWTH_CYCLE',
                    'status' => $activeCycleModel->status->value ?? 'running',
                    'started_at' => $activeCycleModel->started_at?->toIso8601String(),
                    'planting_at' => $activeCycleModel->planting_at?->toIso8601String(),
                    'expected_harvest_at' => $activeCycleModel->expected_harvest_at?->toIso8601String(),
                    'batch_label' => $activeCycleModel->batch_label,
                    'notes' => $activeCycleModel->notes,
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
                                    $parts[] = sprintf('pH %.1f–%.1f', (float)$t['min'], (float)$t['max']);
                                }
                            }

                            // EC (обязательный)
                            if (isset($subs['ec']['enabled']) && $subs['ec']['enabled'] === true && isset($subs['ec']['targets']) && is_array($subs['ec']['targets'])) {
                                $t = $subs['ec']['targets'];
                                if (isset($t['min']) && isset($t['max'])) {
                                    $parts[] = sprintf('EC %.1f–%.1f', (float)$t['min'], (float)$t['max']);
                                }
                            }

                            // Климат (опциональный)
                            if (isset($subs['climate']['enabled']) && $subs['climate']['enabled'] === true && isset($subs['climate']['targets']) && is_array($subs['climate']['targets'])) {
                                $t = $subs['climate']['targets'];
                                if (isset($t['temperature']) && isset($t['humidity'])) {
                                    $parts[] = sprintf('Климат t=%.1f°C, RH=%.0f%%', (float)$t['temperature'], (float)$t['humidity']);
                                }
                            }

                            // Освещение (опциональный)
                            if (isset($subs['lighting']['enabled']) && $subs['lighting']['enabled'] === true && isset($subs['lighting']['targets']) && is_array($subs['lighting']['targets'])) {
                                $t = $subs['lighting']['targets'];
                                if (isset($t['hours_on']) && isset($t['hours_off'])) {
                                    $parts[] = sprintf('Свет %.1fч / пауза %.1fч', (float)$t['hours_on'], (float)$t['hours_off']);
                                }
                            }

                            // Полив (обязательный)
                            if (isset($subs['irrigation']['enabled']) && $subs['irrigation']['enabled'] === true && isset($subs['irrigation']['targets']) && is_array($subs['irrigation']['targets'])) {
                                $t = $subs['irrigation']['targets'];
                                if (isset($t['interval_minutes']) && isset($t['duration_seconds'])) {
                                    $parts[] = sprintf('Полив каждые %d мин, %d с', (int)$t['interval_minutes'], (int)$t['duration_seconds']);
                                }
                            }

                            if (!empty($parts)) {
                                $message = implode('; ', $parts);
                            }
                        }

                        if (!$message) {
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

            // Загружаем активный цикл выращивания
            $activeGrowCycle = \App\Models\GrowCycle::where('zone_id', $zone->id)
                ->whereIn('status', ['PLANNED', 'RUNNING', 'PAUSED'])
                ->latest('started_at')
                ->first();

            // Логируем данные перед отправкой в Inertia
            \Log::info('Sending zone data to Inertia', [
                'zone_id' => $zone->id,
                'zone_name' => $zone->name,
                'has_active_grow_cycle' => $activeGrowCycle !== null,
                'active_grow_cycle' => $activeGrowCycle ? [
                    'id' => $activeGrowCycle->id,
                    'status' => $activeGrowCycle->status,
                    'recipe_revision_id' => $activeGrowCycle->recipe_revision_id,
                    'current_phase_id' => $activeGrowCycle->current_phase_id,
                ] : null,
                'has_active_grow_cycle' => $activeGrowCycle !== null,
            ]);

            return Inertia::render('Zones/Show', [
                'auth' => ['user' => ['role' => auth()->user()->role ?? 'viewer']],
                'zoneId' => $zoneIdInt,
                'zone' => $zone, // Используем модель - Inertia правильно сериализует отношения
                'telemetry' => $telemetryLast,
                'targets' => $targets,
                'current_phase' => $currentPhaseNormalized,
                'active_cycle' => $activeCycle,
                'active_grow_cycle' => $activeGrowCycle,
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
                    if (!$user->isAdmin()) {
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
                    if (!$user->isAdmin()) {
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
