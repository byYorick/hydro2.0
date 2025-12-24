<?php

namespace App\Http\Controllers;

use App\Helpers\ZoneAccessHelper;
use App\Models\Greenhouse;
use Illuminate\Http\JsonResponse;
use Illuminate\Http\Request;
use Illuminate\Http\Response;

class GreenhouseController extends Controller
{
    public function index(Request $request): JsonResponse
    {
        $user = $request->user();
        if (!$user) {
            return response()->json([
                'status' => 'error',
                'message' => 'Unauthorized',
            ], 401);
        }
        
        // Получаем доступные зоны для пользователя
        $accessibleZoneIds = ZoneAccessHelper::getAccessibleZoneIds($user);
        
        // Фильтруем теплицы по доступным зонам
        $query = Greenhouse::query();
        
        // Если пользователь не админ, фильтруем по доступным зонам
        if (!$user->isAdmin()) {
            $query->whereHas('zones', function ($q) use ($accessibleZoneIds) {
                $q->whereIn('id', $accessibleZoneIds);
            });
        }
        
        $items = $query->latest('id')->paginate(25);
        return response()->json(['status' => 'ok', 'data' => $items]);
    }

    public function store(Request $request): JsonResponse
    {
        $user = $request->user();
        if (!$user) {
            return response()->json([
                'status' => 'error',
                'message' => 'Unauthorized',
            ], 401);
        }
        
        // Права доступа проверяются на уровне маршрута (middleware role:operator,admin,agronomist,engineer)
        
        $data = $request->validate([
            'uid' => ['required', 'string', 'max:64', 'unique:greenhouses,uid'],
            'name' => ['required', 'string', 'max:255'],
            'timezone' => ['nullable', 'string', 'max:128'],
            'type' => ['nullable', 'string', 'max:64'],
            'coordinates' => ['nullable', 'array'],
            'description' => ['nullable', 'string'],
        ]);
        
        // Генерируем уникальный provisioning_token для регистрации нод
        // Этот токен не должен быть доступен через API (скрыт в модели)
        $data['provisioning_token'] = 'gh_' . \Illuminate\Support\Str::random(32);
        
        $greenhouse = Greenhouse::create($data);
        return response()->json(['status' => 'ok', 'data' => $greenhouse], Response::HTTP_CREATED);
    }

    public function show(Request $request, Greenhouse $greenhouse): JsonResponse
    {
        $user = $request->user();
        if (!$user) {
            return response()->json([
                'status' => 'error',
                'message' => 'Unauthorized',
            ], 401);
        }
        
        // Проверяем доступ к теплице
        if (!ZoneAccessHelper::canAccessGreenhouse($user, $greenhouse)) {
            return response()->json([
                'status' => 'error',
                'message' => 'Forbidden: Access denied to this greenhouse',
            ], 403);
        }
        
        $greenhouse->load('zones');
        return response()->json(['status' => 'ok', 'data' => $greenhouse]);
    }

    public function update(Request $request, Greenhouse $greenhouse): JsonResponse
    {
        $user = $request->user();
        if (!$user) {
            return response()->json([
                'status' => 'error',
                'message' => 'Unauthorized',
            ], 401);
        }
        
        // Проверяем доступ к теплице
        if (!ZoneAccessHelper::canAccessGreenhouse($user, $greenhouse)) {
            return response()->json([
                'status' => 'error',
                'message' => 'Forbidden: Access denied to this greenhouse',
            ], 403);
        }
        
        $data = $request->validate([
            'uid' => ['sometimes', 'string', 'max:64', 'unique:greenhouses,uid,'.$greenhouse->id],
            'name' => ['sometimes', 'string', 'max:255'],
            'timezone' => ['nullable', 'string', 'max:128'],
            'type' => ['nullable', 'string', 'max:64'],
            'coordinates' => ['nullable', 'array'],
            'description' => ['nullable', 'string'],
        ]);
        $greenhouse->update($data);
        return response()->json(['status' => 'ok', 'data' => $greenhouse]);
    }

    public function destroy(Request $request, Greenhouse $greenhouse): JsonResponse
    {
        $user = $request->user();
        if (!$user) {
            return response()->json([
                'status' => 'error',
                'message' => 'Unauthorized',
            ], 401);
        }
        
        // Только админы могут удалять теплицы
        if (!$user->isAdmin()) {
            return response()->json([
                'status' => 'error',
                'message' => 'Forbidden: Only administrators can delete greenhouses',
            ], 403);
        }
        
        // Проверяем доступ к теплице
        if (!ZoneAccessHelper::canAccessGreenhouse($user, $greenhouse)) {
            return response()->json([
                'status' => 'error',
                'message' => 'Forbidden: Access denied to this greenhouse',
            ], 403);
        }
        
        // Проверяем наличие привязанных зон
        $zonesCount = \App\Models\Zone::where('greenhouse_id', $greenhouse->id)->count();
        if ($zonesCount > 0) {
            return response()->json([
                'status' => 'error',
                'message' => "Cannot delete greenhouse: it has {$zonesCount} associated zone(s). Please delete or reassign zones first.",
            ], Response::HTTP_UNPROCESSABLE_ENTITY);
        }
        
        // Проверяем наличие привязанных узлов (на всякий случай, если есть прямая связь)
        // Обычно узлы привязаны через зоны, но проверка не помешает
        $nodesCount = \App\Models\DeviceNode::whereHas('zone', function ($q) use ($greenhouse) {
            $q->where('greenhouse_id', $greenhouse->id);
        })->count();
        
        if ($nodesCount > 0) {
            return response()->json([
                'status' => 'error',
                'message' => "Cannot delete greenhouse: it has {$nodesCount} associated node(s) through zones. Please delete or reassign nodes first.",
            ], Response::HTTP_UNPROCESSABLE_ENTITY);
        }
        
        $greenhouse->delete();
        return response()->json(['status' => 'ok']);
    }

    public function dashboard(Request $request, Greenhouse $greenhouse): JsonResponse
    {
        $user = $request->user();
        if (!$user) {
            return response()->json([
                'status' => 'error',
                'message' => 'Unauthorized',
            ], 401);
        }

        // Проверяем доступ к теплице
        if (!ZoneAccessHelper::canAccessGreenhouse($user, $greenhouse)) {
            return response()->json([
                'status' => 'error',
                'message' => 'Forbidden: Access denied to this greenhouse',
            ], 403);
        }

        // Получаем зоны с активными рецептами
        $zones = \App\Models\Zone::query()
            ->where('greenhouse_id', $greenhouse->id)
            ->with([
                'recipeInstance.recipe.phases' => function ($query) {
                    $query->orderBy('phase_index');
                },
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
            ->orderBy('name')
            ->get();

        $zoneIds = $zones->pluck('id')->toArray();

        // Получаем телеметрию для всех зон
        $telemetryByZone = [];
        if (!empty($zoneIds)) {
            $telemetryAll = \App\Models\TelemetryLast::query()
                ->whereIn('zone_id', $zoneIds)
                ->get(['zone_id', 'metric_type', 'value']);

            foreach ($telemetryAll as $metric) {
                $key = strtolower($metric->metric_type ?? '');
                if (!isset($telemetryByZone[$metric->zone_id])) {
                    $telemetryByZone[$metric->zone_id] = [
                        'ph' => null,
                        'ec' => null,
                        'temperature' => null,
                        'humidity' => null,
                        'co2' => null,
                    ];
                }

                if ($key === 'ph') {
                    $telemetryByZone[$metric->zone_id]['ph'] = (float) $metric->value;
                } elseif ($key === 'ec') {
                    $telemetryByZone[$metric->zone_id]['ec'] = (float) $metric->value;
                } elseif (in_array($key, ['temp', 'temperature', 'air_temperature'])) {
                    $telemetryByZone[$metric->zone_id]['temperature'] = (float) $metric->value;
                } elseif (in_array($key, ['humidity', 'rh'])) {
                    $telemetryByZone[$metric->zone_id]['humidity'] = (float) $metric->value;
                } elseif ($key === 'co2') {
                    $telemetryByZone[$metric->zone_id]['co2'] = (float) $metric->value;
                }
            }
        }

        // Получаем топ-2 активных алерта для каждой зоны
        $alertsByZone = [];
        if (!empty($zoneIds)) {
            $alerts = \App\Models\Alert::query()
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
                        'code' => $alert->code,
                        'details' => $alert->details,
                        'created_at' => $alert->created_at?->toIso8601String(),
                    ];
                })->toArray();
            }
        }

        // Формируем данные для каждой зоны
        $zonesData = $zones->map(function ($zone) use ($telemetryByZone, $alertsByZone) {
            $recipeInstance = $zone->recipeInstance;
            $currentPhase = null;
            $cycleProgress = null;
            $stageInfo = null;
            $etaToNextStage = null;
            $etaToHarvest = null;

            if ($recipeInstance && $recipeInstance->recipe && $recipeInstance->recipe->phases) {
                $currentPhaseIndex = $recipeInstance->current_phase_index ?? -1;
                $phases = $recipeInstance->recipe->phases->sortBy('phase_index');
                $currentPhase = $phases->firstWhere('phase_index', $currentPhaseIndex);

                if ($currentPhase && $recipeInstance->started_at) {
                    // Вычисляем прогресс цикла
                    $totalHours = $phases->sum('duration_hours');
                    $elapsedHours = $recipeInstance->started_at->diffInHours(now(), false);
                    
                    if ($totalHours > 0 && $elapsedHours >= 0) {
                        // Вычисляем прошедшие часы до текущей фазы
                        $completedHours = $phases->takeWhile(function ($phase) use ($currentPhaseIndex) {
                            return $phase->phase_index < $currentPhaseIndex;
                        })->sum('duration_hours');

                        // Прогресс в текущей фазе
                        $phaseProgress = 0;
                        if ($currentPhase->duration_hours > 0) {
                            $timeInPhase = $elapsedHours - $completedHours;
                            $phaseProgress = min(100, max(0, ($timeInPhase / $currentPhase->duration_hours) * 100));
                        }

                        // Общий прогресс
                        $currentPhaseCompleted = ($currentPhase->duration_hours ?? 0) * ($phaseProgress / 100);
                        $totalCompleted = $completedHours + $currentPhaseCompleted;
                        $cycleProgress = min(100, max(0, ($totalCompleted / $totalHours) * 100));

                        // ETA до следующей стадии
                        $remainingInPhase = ($currentPhase->duration_hours ?? 0) * (1 - $phaseProgress / 100);
                        if ($remainingInPhase > 0) {
                            $etaToNextStage = \Carbon\Carbon::now()->addHours($remainingInPhase)->toIso8601String();
                        }

                        // ETA до сбора (конец последней фазы)
                        $remainingHours = $totalHours - $totalCompleted;
                        if ($remainingHours > 0) {
                            $etaToHarvest = \Carbon\Carbon::now()->addHours($remainingHours)->toIso8601String();
                        }
                    }
                }

                // Определяем стадию по фазе
                if ($currentPhase) {
                    $phaseName = strtolower($currentPhase->name);
                    if (str_contains($phaseName, 'посадк') || str_contains($phaseName, 'germ') || str_contains($phaseName, 'seed')) {
                        $stageInfo = ['id' => 'planting', 'label' => 'Посадка'];
                    } elseif (str_contains($phaseName, 'укорен') || str_contains($phaseName, 'root') || str_contains($phaseName, 'seedling')) {
                        $stageInfo = ['id' => 'rooting', 'label' => 'Укоренение'];
                    } elseif (str_contains($phaseName, 'вега') || str_contains($phaseName, 'veg') || str_contains($phaseName, 'рост')) {
                        $stageInfo = ['id' => 'veg', 'label' => 'Вега'];
                    } elseif (str_contains($phaseName, 'цвет') || str_contains($phaseName, 'flower') || str_contains($phaseName, 'bloom')) {
                        $stageInfo = ['id' => 'flowering', 'label' => 'Цветение'];
                    } elseif (str_contains($phaseName, 'сбор') || str_contains($phaseName, 'harvest') || str_contains($phaseName, 'finish')) {
                        $stageInfo = ['id' => 'harvest', 'label' => 'Сбор'];
                    } else {
                        // По умолчанию используем индекс фазы
                        $defaultStages = ['planting', 'rooting', 'veg', 'flowering', 'harvest'];
                        $stageIndex = min($currentPhaseIndex, count($defaultStages) - 1);
                        $stageInfo = ['id' => $defaultStages[$stageIndex], 'label' => $defaultStages[$stageIndex]];
                    }
                }
            }

            // Получаем цели текущей фазы
            $targets = null;
            if ($currentPhase && $currentPhase->targets) {
                $targets = $currentPhase->targets;
            }

            return [
                'id' => $zone->id,
                'name' => $zone->name,
                'status' => $zone->status,
                'telemetry' => $telemetryByZone[$zone->id] ?? null,
                'targets' => $targets,
                'stage' => $stageInfo,
                'cycle_progress' => $cycleProgress,
                'current_phase' => $currentPhase ? [
                    'index' => $currentPhase->phase_index,
                    'name' => $currentPhase->name,
                ] : null,
                'eta_to_next_stage' => $etaToNextStage,
                'eta_to_harvest' => $etaToHarvest,
                'alerts' => $alertsByZone[$zone->id] ?? [],
                'alerts_count' => $zone->alerts_count ?? 0,
                'nodes_online' => $zone->nodes_online ?? 0,
                'nodes_total' => $zone->nodes_total ?? 0,
                'recipe' => $recipeInstance?->recipe ? [
                    'id' => $recipeInstance->recipe->id,
                    'name' => $recipeInstance->recipe->name,
                ] : null,
            ];
        });

        return response()->json([
            'status' => 'ok',
            'data' => [
                'greenhouse' => [
                    'id' => $greenhouse->id,
                    'name' => $greenhouse->name,
                    'description' => $greenhouse->description,
                ],
                'zones' => $zonesData,
            ],
        ]);
    }
}


