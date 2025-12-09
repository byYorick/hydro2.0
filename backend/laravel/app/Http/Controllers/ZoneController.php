<?php

namespace App\Http\Controllers;

use App\Helpers\ZoneAccessHelper;
use App\Models\Zone;
use App\Services\ZoneService;
use Illuminate\Http\JsonResponse;
use Illuminate\Http\Request;
use Illuminate\Http\Response;
use Illuminate\Support\Facades\Log;

class ZoneController extends Controller
{
    public function __construct(
        private ZoneService $zoneService
    ) {
    }

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
        
        // Валидация query параметров
        $validated = $request->validate([
            'greenhouse_id' => ['nullable', 'integer', 'exists:greenhouses,id'],
            'status' => ['nullable', 'string', 'in:online,offline,warning'],
            'search' => ['nullable', 'string', 'max:255'],
        ]);
        
        // Eager loading для предотвращения N+1 запросов
        $query = Zone::query()
            ->withCount('nodes') // Счетчик узлов
            ->with(['greenhouse:id,name', 'preset:id,name']); // Загружаем только нужные поля
        
        // Фильтруем зоны по доступным для пользователя
        if (!$user->isAdmin()) {
            $query->whereIn('id', $accessibleZoneIds);
        }
        
        if (isset($validated['greenhouse_id'])) {
            // Дополнительно проверяем доступ к теплице
            if (!$user->isAdmin() && !ZoneAccessHelper::canAccessGreenhouse($user, $validated['greenhouse_id'])) {
                return response()->json([
                    'status' => 'error',
                    'message' => 'Forbidden: Access denied to this greenhouse',
                ], 403);
            }
            $query->where('greenhouse_id', $validated['greenhouse_id']);
        }
        if (isset($validated['status'])) {
            $query->where('status', $validated['status']);
        }
        
        // Поиск по имени или описанию
        if (isset($validated['search']) && $validated['search']) {
            // Экранируем специальные символы LIKE для защиты от SQL injection
            $searchTerm = addcslashes($validated['search'], '%_');
            $query->where(function ($q) use ($searchTerm) {
                $q->where('name', 'ILIKE', "%{$searchTerm}%")
                  ->orWhere('description', 'ILIKE', "%{$searchTerm}%");
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
        
        $data = $request->validate([
            'greenhouse_id' => ['nullable', 'integer', 'exists:greenhouses,id'],
            'preset_id' => ['nullable', 'integer', 'exists:presets,id'],
            'name' => ['required', 'string', 'max:255'],
            'description' => ['nullable', 'string'],
            'status' => ['nullable', 'string', 'max:32'],
        ]);
        
        // Проверяем доступ к теплице, если указана
        if (isset($data['greenhouse_id'])) {
            if (!ZoneAccessHelper::canAccessGreenhouse($user, $data['greenhouse_id'])) {
                return response()->json([
                    'status' => 'error',
                    'message' => 'Forbidden: Access denied to this greenhouse',
                ], 403);
            }
        }
        
        $zone = $this->zoneService->create($data);
        return response()->json(['status' => 'ok', 'data' => $zone], Response::HTTP_CREATED);
    }

    public function show(Request $request, Zone $zone): JsonResponse
    {
        $user = $request->user();
        if (!$user) {
            return response()->json([
                'status' => 'error',
                'message' => 'Unauthorized',
            ], 401);
        }
        
        // Проверяем доступ к зоне
        if (!ZoneAccessHelper::canAccessZone($user, $zone)) {
            return response()->json([
                'status' => 'error',
                'message' => 'Forbidden: Access denied to this zone',
            ], 403);
        }
        
        $zone->load(['greenhouse', 'preset', 'nodes', 'recipeInstance.recipe.phases']);
        return response()->json(['status' => 'ok', 'data' => $zone]);
    }

    public function update(Request $request, Zone $zone): JsonResponse
    {
        $user = $request->user();
        if (!$user) {
            return response()->json([
                'status' => 'error',
                'message' => 'Unauthorized',
            ], 401);
        }
        
        // Проверяем доступ к зоне
        if (!ZoneAccessHelper::canAccessZone($user, $zone)) {
            return response()->json([
                'status' => 'error',
                'message' => 'Forbidden: Access denied to this zone',
            ], 403);
        }
        
        $data = $request->validate([
            'greenhouse_id' => ['nullable', 'integer', 'exists:greenhouses,id'],
            'name' => ['sometimes', 'string', 'max:255'],
            'description' => ['nullable', 'string'],
            'status' => ['nullable', 'string', 'max:32'],
        ]);
        
        // Проверяем доступ к новой теплице, если меняется
        if (isset($data['greenhouse_id']) && $data['greenhouse_id'] !== $zone->greenhouse_id) {
            if (!ZoneAccessHelper::canAccessGreenhouse($user, $data['greenhouse_id'])) {
                return response()->json([
                    'status' => 'error',
                    'message' => 'Forbidden: Access denied to target greenhouse',
                ], 403);
            }
        }
        
        $zone = $this->zoneService->update($zone, $data);
        return response()->json(['status' => 'ok', 'data' => $zone]);
    }

    public function destroy(Request $request, Zone $zone): JsonResponse
    {
        $user = $request->user();
        if (!$user) {
            return response()->json([
                'status' => 'error',
                'message' => 'Unauthorized',
            ], 401);
        }
        
        // Проверяем доступ к зоне
        if (!ZoneAccessHelper::canAccessZone($user, $zone)) {
            return response()->json([
                'status' => 'error',
                'message' => 'Forbidden: Access denied to this zone',
            ], 403);
        }
        
        try {
            $this->zoneService->delete($zone);
            return response()->json(['status' => 'ok']);
        } catch (\DomainException $e) {
            return response()->json([
                'status' => 'error',
                'message' => $e->getMessage(),
            ], Response::HTTP_UNPROCESSABLE_ENTITY);
        }
    }

    public function attachRecipe(Request $request, Zone $zone): JsonResponse
    {
        $user = $request->user();
        if (!$user) {
            return response()->json([
                'status' => 'error',
                'message' => 'Unauthorized',
            ], 401);
        }
        
        // Проверяем доступ к зоне
        if (!ZoneAccessHelper::canAccessZone($user, $zone)) {
            return response()->json([
                'status' => 'error',
                'message' => 'Forbidden: Access denied to this zone',
            ], 403);
        }
        
        try {
            $data = $request->validate([
                'recipe_id' => ['required', 'integer', 'exists:recipes,id'],
                'start_at' => ['nullable', 'date'],
            ]);
            
            $instance = $this->zoneService->attachRecipe(
                $zone,
                $data['recipe_id'],
                isset($data['start_at']) ? new \DateTime($data['start_at']) : null
            );
            
            // Загружаем обновленную зону с recipeInstance
            $zone->refresh();
            $zone->load(['recipeInstance.recipe']);
            
            return response()->json([
                'status' => 'ok',
                'data' => [
                    'zone_id' => $zone->id,
                    'recipe_instance_id' => $instance->id,
                    'recipe_id' => $instance->recipe_id,
                ]
            ]);
        } catch (\Exception $e) {
            Log::error('Failed to attach recipe', [
                'zone_id' => $zone->id,
                'error' => $e->getMessage(),
                'trace' => $e->getTraceAsString()
            ]);
            
            return response()->json([
                'status' => 'error',
                'message' => $e->getMessage(),
            ], Response::HTTP_UNPROCESSABLE_ENTITY);
        }
    }

    public function changePhase(Request $request, Zone $zone): JsonResponse
    {
        $user = $request->user();
        if (!$user) {
            return response()->json([
                'status' => 'error',
                'message' => 'Unauthorized',
            ], 401);
        }
        
        // Проверяем доступ к зоне
        if (!ZoneAccessHelper::canAccessZone($user, $zone)) {
            return response()->json([
                'status' => 'error',
                'message' => 'Forbidden: Access denied to this zone',
            ], 403);
        }
        
        $data = $request->validate([
            'phase_index' => ['required', 'integer', 'min:0'],
        ]);
        try {
            $this->zoneService->changePhase($zone, $data['phase_index']);
            return response()->json(['status' => 'ok']);
        } catch (\DomainException $e) {
            return response()->json([
                'status' => 'error',
                'message' => $e->getMessage(),
            ], Response::HTTP_UNPROCESSABLE_ENTITY);
        }
    }

    public function nextPhase(Request $request, Zone $zone): JsonResponse
    {
        $user = $request->user();
        if (!$user) {
            return response()->json([
                'status' => 'error',
                'message' => 'Unauthorized',
            ], 401);
        }
        
        // Проверяем доступ к зоне
        if (!ZoneAccessHelper::canAccessZone($user, $zone)) {
            return response()->json([
                'status' => 'error',
                'message' => 'Forbidden: Access denied to this zone',
            ], 403);
        }
        
        try {
            $instance = $this->zoneService->nextPhase($zone);
            return response()->json(['status' => 'ok', 'data' => $instance]);
        } catch (\DomainException $e) {
            return response()->json([
                'status' => 'error',
                'message' => $e->getMessage(),
            ], Response::HTTP_UNPROCESSABLE_ENTITY);
        }
    }

    public function pause(Request $request, Zone $zone): JsonResponse
    {
        $user = $request->user();
        if (!$user) {
            return response()->json([
                'status' => 'error',
                'message' => 'Unauthorized',
            ], 401);
        }
        
        // Проверяем доступ к зоне
        if (!ZoneAccessHelper::canAccessZone($user, $zone)) {
            return response()->json([
                'status' => 'error',
                'message' => 'Forbidden: Access denied to this zone',
            ], 403);
        }
        
        try {
            $zone = $this->zoneService->pause($zone);
            return response()->json(['status' => 'ok', 'data' => $zone]);
        } catch (\DomainException $e) {
            return response()->json([
                'status' => 'error',
                'message' => $e->getMessage(),
            ], Response::HTTP_UNPROCESSABLE_ENTITY);
        }
    }

    public function resume(Request $request, Zone $zone): JsonResponse
    {
        $user = $request->user();
        if (!$user) {
            return response()->json([
                'status' => 'error',
                'message' => 'Unauthorized',
            ], 401);
        }
        
        // Проверяем доступ к зоне
        if (!ZoneAccessHelper::canAccessZone($user, $zone)) {
            return response()->json([
                'status' => 'error',
                'message' => 'Forbidden: Access denied to this zone',
            ], 403);
        }
        
        try {
            $zone = $this->zoneService->resume($zone);
            return response()->json(['status' => 'ok', 'data' => $zone]);
        } catch (\DomainException $e) {
            return response()->json([
                'status' => 'error',
                'message' => $e->getMessage(),
            ], Response::HTTP_UNPROCESSABLE_ENTITY);
        }
    }

    public function health(Request $request, Zone $zone): JsonResponse
    {
        $user = $request->user();
        if (!$user) {
            return response()->json([
                'status' => 'error',
                'message' => 'Unauthorized',
            ], 401);
        }
        
        // Проверяем доступ к зоне
        if (!ZoneAccessHelper::canAccessZone($user, $zone)) {
            return response()->json([
                'status' => 'error',
                'message' => 'Forbidden: Access denied to this zone',
            ], 403);
        }
        
        // Eager loading для предотвращения N+1 запросов
        $zone->load([
            'nodes' => function ($query) {
                $query->select('id', 'zone_id', 'status'); // Оптимизация: загружаем только нужные поля
            },
            'alerts' => function ($query) {
                $query->where('status', 'ACTIVE')->select('id', 'zone_id', 'status'); // Оптимизация
            }
        ]);
        
        // Возвращаем детальную информацию о здоровье зоны
        // Используем уже загруженные отношения вместо новых запросов
        return response()->json([
            'status' => 'ok',
            'data' => [
                'zone_id' => $zone->id,
                'health_score' => $zone->health_score,
                'health_status' => $zone->health_status,
                'zone_status' => $zone->status,
                'active_alerts_count' => $zone->alerts->count(), // Используем загруженную коллекцию
                'nodes_online' => $zone->nodes->where('status', 'online')->count(), // Используем загруженную коллекцию
                'nodes_total' => $zone->nodes->count(), // Используем загруженную коллекцию
            ],
        ]);
    }

    public function fill(Request $request, Zone $zone): JsonResponse
    {
        $user = $request->user();
        if (!$user) {
            return response()->json([
                'status' => 'error',
                'message' => 'Unauthorized',
            ], 401);
        }
        
        // Проверяем доступ к зоне
        if (!ZoneAccessHelper::canAccessZone($user, $zone)) {
            return response()->json([
                'status' => 'error',
                'message' => 'Forbidden: Access denied to this zone',
            ], 403);
        }
        
        $data = $request->validate([
            'target_level' => ['required', 'numeric', 'min:0.1', 'max:1.0'],
            'max_duration_sec' => ['nullable', 'integer', 'min:10', 'max:600'],
        ]);

        // Выполняем операцию асинхронно через очередь для предотвращения блокировки PHP-FPM
        $jobId = \Illuminate\Support\Str::uuid()->toString();
        \App\Jobs\ZoneOperationJob::dispatch($zone->id, 'fill', $data, $jobId);
        
        return response()->json([
            'status' => 'ok',
            'message' => 'Fill operation queued',
            'job_id' => $jobId,
        ], Response::HTTP_ACCEPTED);
    }

    public function drain(Request $request, Zone $zone): JsonResponse
    {
        $user = $request->user();
        if (!$user) {
            return response()->json([
                'status' => 'error',
                'message' => 'Unauthorized',
            ], 401);
        }
        
        // Проверяем доступ к зоне
        if (!ZoneAccessHelper::canAccessZone($user, $zone)) {
            return response()->json([
                'status' => 'error',
                'message' => 'Forbidden: Access denied to this zone',
            ], 403);
        }
        
        $data = $request->validate([
            'target_level' => ['required', 'numeric', 'min:0.0', 'max:0.9'],
            'max_duration_sec' => ['nullable', 'integer', 'min:10', 'max:600'],
        ]);

        // Выполняем операцию асинхронно через очередь для предотвращения блокировки PHP-FPM
        $jobId = \Illuminate\Support\Str::uuid()->toString();
        \App\Jobs\ZoneOperationJob::dispatch($zone->id, 'drain', $data, $jobId);
        
        return response()->json([
            'status' => 'ok',
            'message' => 'Drain operation queued',
            'job_id' => $jobId,
        ], Response::HTTP_ACCEPTED);
    }

    public function calibrateFlow(Request $request, Zone $zone): JsonResponse
    {
        $user = $request->user();
        if (!$user) {
            return response()->json([
                'status' => 'error',
                'message' => 'Unauthorized',
            ], 401);
        }
        
        // Проверяем доступ к зоне
        if (!ZoneAccessHelper::canAccessZone($user, $zone)) {
            return response()->json([
                'status' => 'error',
                'message' => 'Forbidden: Access denied to this zone',
            ], 403);
        }
        
        $data = $request->validate([
            'node_id' => ['required', 'integer', 'exists:nodes,id'],
            'channel' => ['required', 'string', 'max:128'],
            'pump_duration_sec' => ['nullable', 'integer', 'min:5', 'max:60'],
        ]);
        
        // Проверяем доступ к ноде
        $node = \App\Models\DeviceNode::find($data['node_id']);
        if ($node && !ZoneAccessHelper::canAccessNode($user, $node)) {
            return response()->json([
                'status' => 'error',
                'message' => 'Forbidden: Access denied to this node',
            ], 403);
        }

        // Выполняем операцию асинхронно через очередь для предотвращения блокировки PHP-FPM
        $jobId = \Illuminate\Support\Str::uuid()->toString();
        \App\Jobs\ZoneOperationJob::dispatch($zone->id, 'calibrateFlow', $data, $jobId);
        
        return response()->json([
            'status' => 'ok',
            'message' => 'Calibrate flow operation queued',
            'job_id' => $jobId,
        ], Response::HTTP_ACCEPTED);
    }

    /**
     * Получить информацию о циклах зоны
     * GET /api/zones/{id}/cycles
     */
    public function cycles(Request $request, Zone $zone): JsonResponse
    {
        $user = $request->user();
        if (!$user) {
            return response()->json([
                'status' => 'error',
                'message' => 'Unauthorized',
            ], 401);
        }
        
        // Проверяем доступ к зоне
        if (!ZoneAccessHelper::canAccessZone($user, $zone)) {
            return response()->json([
                'status' => 'error',
                'message' => 'Forbidden: Access denied to this zone',
            ], 403);
        }
        
        $cycles = [];
        $settings = $zone->settings ?? [];
        $targets = [];
        
        // Получаем targets из текущей фазы рецепта
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
        
        // Получаем последние команды для вычисления last_run
        $lastCommands = \App\Models\Command::query()
            ->where('zone_id', $zone->id)
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
        
        return response()->json([
            'status' => 'ok',
            'data' => $cycles,
        ]);
    }
}


