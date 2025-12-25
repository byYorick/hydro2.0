<?php

namespace App\Http\Controllers;

use App\Helpers\ZoneAccessHelper;
use App\Models\Zone;
use App\Models\ZoneRecipeInstance;
use App\Services\ZoneService;
use App\Services\ZoneReadinessService;
use Illuminate\Http\JsonResponse;
use Illuminate\Http\Request;
use Illuminate\Http\Response;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Log;
use Illuminate\Support\Facades\Schema;

class ZoneController extends Controller
{
    public function __construct(
        private ZoneService $zoneService,
        private ZoneReadinessService $readinessService
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
        
        $zone->load(['greenhouse', 'preset', 'nodes', 'recipeInstance.recipe.phases', 'activeGrowCycle']);
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
            
            // Создаем zone_event для изменения фазы (уже создается в nextPhase, но на всякий случай проверяем)
            // WebSocket уведомление будет отправлено через ZoneUpdated event
            
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
            Log::warning('Zone pause failed: DomainException', [
                'zone_id' => $zone->id,
                'error' => $e->getMessage()
            ]);
            return response()->json([
                'status' => 'error',
                'message' => $e->getMessage(),
            ], Response::HTTP_UNPROCESSABLE_ENTITY);
        } catch (\Exception $e) {
            Log::error('Zone pause failed: Unexpected error', [
                'zone_id' => $zone->id,
                'error' => $e->getMessage(),
                'trace' => $e->getTraceAsString()
            ]);
            return response()->json([
                'status' => 'error',
                'message' => 'An error occurred while pausing zone: ' . $e->getMessage(),
            ], 500);
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

    /**
     * Завершить grow-cycle (harvest)
     * POST /api/zones/{zone}/harvest
     */
    public function harvest(Request $request, Zone $zone): JsonResponse
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
            $zone = $this->zoneService->harvest($zone);
            return response()->json(['status' => 'ok', 'data' => $zone]);
        } catch (\DomainException $e) {
            return response()->json([
                'status' => 'error',
                'message' => $e->getMessage(),
            ], Response::HTTP_UNPROCESSABLE_ENTITY);
        }
    }

    /**
     * Запустить grow-cycle для зоны
     * POST /api/zones/{zone}/start
     */
    public function start(Request $request, Zone $zone): JsonResponse
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

        // Проверяем готовность зоны
        $readiness = $this->readinessService->checkZoneReadiness($zone);

        // Если есть критические ошибки - возвращаем 422
        if (!$readiness['ready']) {
            return response()->json([
                'status' => 'error',
                'message' => 'Zone is not ready to start',
                'errors' => $readiness['errors'],
                'warnings' => $readiness['warnings'],
            ], 422);
        }

        return DB::transaction(function () use ($zone, $readiness) {
            // Если есть активный recipe instance - обновляем его статус
            if ($zone->recipeInstance) {
                // Убеждаемся что started_at установлен
                if (!$zone->recipeInstance->started_at) {
                    $zone->recipeInstance->update(['started_at' => now()]);
                }
            } else {
                // Если рецепт не привязан, создаем пустой instance (опционально)
                // Или просто запускаем зону без рецепта
                Log::info('Zone started without recipe instance', [
                    'zone_id' => $zone->id
                ]);
            }

            // Обновляем статус зоны на RUNNING
            $zone->update(['status' => 'RUNNING']);
            $zone->refresh();
            $zone->load(['recipeInstance.recipe']);

            // Создаем zone_event
            $hasPayloadJson = Schema::hasColumn('zone_events', 'payload_json');
            
            $eventPayload = json_encode([
                'zone_id' => $zone->id,
                'status' => 'RUNNING',
                'warnings' => $readiness['warnings'],
            ]);
            
            $eventData = [
                'zone_id' => $zone->id,
                'type' => 'CYCLE_STARTED',
                'created_at' => now(),
            ];
            
            if ($hasPayloadJson) {
                $eventData['payload_json'] = $eventPayload;
            } else {
                $eventData['details'] = $eventPayload;
            }
            
            DB::table('zone_events')->insert($eventData);

            Log::info('Zone cycle started', [
                'zone_id' => $zone->id,
                'status' => 'RUNNING',
                'warnings_count' => count($readiness['warnings']),
            ]);

            return response()->json([
                'status' => 'ok',
                'data' => [
                    'zone_id' => $zone->id,
                    'status' => $zone->status,
                    'warnings' => $readiness['warnings'],
                ],
            ]);
        });
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

    /**
     * Получить unassigned errors для зоны
     * GET /api/zones/{zone}/unassigned-errors
     */
    public function unassignedErrors(Request $request, Zone $zone): JsonResponse
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
        
        // Получаем ноды зоны
        $nodeIds = $zone->nodes()->pluck('id')->toArray();
        
        // Если у зоны нет нод, возвращаем пустой результат
        if (empty($nodeIds)) {
            return response()->json([
                'status' => 'ok',
                'data' => [],
                'meta' => [
                    'current_page' => 1,
                    'last_page' => 1,
                    'per_page' => 50,
                    'total' => 0,
                ]
            ]);
        }
        
        // Получаем unassigned errors для нод этой зоны
        $query = DB::table('unassigned_node_errors')
            ->whereIn('node_id', $nodeIds)
            ->select([
                'id',
                'hardware_id',
                'error_message',
                'error_code',
                'severity',
                'topic',
                'last_payload',
                'count',
                'first_seen_at',
                'last_seen_at',
                'node_id',
                'created_at',
                'updated_at'
            ])
            ->orderBy('last_seen_at', 'desc');
        
        // Фильтр по severity
        if ($request->has('severity')) {
            $query->where('severity', $request->input('severity'));
        }
        
        // Фильтр по error_code
        if ($request->has('error_code')) {
            $query->where('error_code', $request->input('error_code'));
        }
        
        // Пагинация
        $perPage = min($request->input('per_page', 50), 100);
        $errors = $query->paginate($perPage);
        
        return response()->json([
            'status' => 'ok',
            'data' => $errors->items(),
            'meta' => [
                'current_page' => $errors->currentPage(),
                'last_page' => $errors->lastPage(),
                'per_page' => $errors->perPage(),
                'total' => $errors->total(),
            ]
        ]);
    }

    /**
     * Получить snapshot состояния зоны для восстановления после reconnect
     * GET /api/zones/{zone}/snapshot
     * 
     * Возвращает:
     * - latest telemetry (per node/channel)
     * - active alerts
     * - last N commands + statuses
     * - device online/offline status
     * - server_ts + snapshot_id
     */
    public function snapshot(Request $request, Zone $zone): JsonResponse
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

        // Формируем snapshot атомарно в одной транзакции
        // Фиксируем server_ts и last_event_id в начале для консистентности
        return DB::transaction(function () use ($zone, $request) {
            $now = now();
            $serverTs = $now->timestamp * 1000; // миллисекунды
            $snapshotId = \Illuminate\Support\Str::uuid()->toString();
            
            // Получаем максимальный last_event_id для зоны на момент формирования snapshot
            // Это курсор событий, который клиент может использовать для catch-up
            $lastEventId = DB::table('zone_events')
                ->where('zone_id', $zone->id)
                ->max('id') ?? 0;

        // Получаем последние значения телеметрии для зоны (per node/channel)
        $telemetryRaw = \App\Models\TelemetryLast::query()
            ->where('zone_id', $zone->id)
            ->select(['node_id', 'channel', 'metric_type', 'value', 'updated_at'])
            ->orderBy('updated_at', 'desc')
            ->get();
        
        // Группируем по node_id, затем по channel
        $telemetry = [];
        foreach ($telemetryRaw as $item) {
            $nodeId = $item->node_id ?? 'unknown';
            $channel = $item->channel ?? 'default';
            
            if (!isset($telemetry[$nodeId])) {
                $telemetry[$nodeId] = [];
            }
            if (!isset($telemetry[$nodeId][$channel])) {
                $telemetry[$nodeId][$channel] = [];
            }
            
            $telemetry[$nodeId][$channel][] = [
                'metric_type' => $item->metric_type,
                'value' => $item->value,
                'updated_at' => $item->updated_at?->toIso8601String(),
            ];
        }

        // Получаем активные алерты
        $activeAlerts = \App\Models\Alert::query()
            ->where('zone_id', $zone->id)
            ->where('status', 'ACTIVE')
            ->select(['id', 'code', 'type', 'details', 'status', 'created_at'])
            ->orderBy('created_at', 'desc')
            ->get()
            ->map(function ($alert) {
                return [
                    'id' => $alert->id,
                    'code' => $alert->code,
                    'type' => $alert->type,
                    'details' => $alert->details,
                    'status' => $alert->status,
                    'created_at' => $alert->created_at?->toIso8601String(),
                ];
            });

            // Получаем последние N команд (по умолчанию 50)
            $commandsLimit = min($request->input('commands_limit', 50), 200);
            
            // Проверяем наличие расширенных полей в таблице commands
            $columns = DB::getSchemaBuilder()->getColumnListing('commands');
            $hasExtendedFields = in_array('error_code', $columns);
            
            $recentCommands = \App\Models\Command::query()
                ->where('zone_id', $zone->id)
                ->select([
                    'id',
                    'cmd_id',
                    'cmd',
                    'status',
                    'node_id',
                    'channel',
                    'params',
                    'sent_at',
                    'ack_at',
                    'failed_at',
                    ...($hasExtendedFields ? ['error_code', 'error_message', 'result_code', 'duration_ms'] : []),
                ])
                ->orderBy('created_at', 'desc')
                ->limit($commandsLimit)
                ->get()
                ->map(function ($command) use ($hasExtendedFields) {
                    $result = [
                        'id' => $command->id,
                        'cmd_id' => $command->cmd_id,
                        'cmd' => $command->cmd,
                        'status' => $command->status,
                        'node_id' => $command->node_id,
                        'channel' => $command->channel,
                        'params' => $command->params,
                        'sent_at' => $command->sent_at?->toIso8601String(),
                        'ack_at' => $command->ack_at?->toIso8601String(),
                        'failed_at' => $command->failed_at?->toIso8601String(),
                    ];
                    
                    if ($hasExtendedFields) {
                        $result['error_code'] = $command->error_code;
                        $result['error_message'] = $command->error_message;
                        $result['result_code'] = $command->result_code;
                        $result['duration_ms'] = $command->duration_ms;
                    }
                    
                    return $result;
                });

            // Получаем статусы устройств (online/offline) - devices_online_state
            $devicesOnlineState = $zone->nodes()
                ->select(['id', 'uid', 'name', 'type', 'status', 'last_seen_at', 'last_heartbeat_at'])
                ->get()
                ->map(function ($node) {
                    return [
                        'id' => $node->id,
                        'uid' => $node->uid,
                        'name' => $node->name,
                        'type' => $node->type,
                        'status' => $node->status, // online/offline
                        'last_seen_at' => $node->last_seen_at?->toIso8601String(),
                        'last_heartbeat_at' => $node->last_heartbeat_at?->toIso8601String(),
                    ];
                });

            // Реструктурируем телеметрию как latest_telemetry_per_channel
            // Группируем по channel, затем по node_id для удобства клиента
            $latestTelemetryPerChannel = [];
            foreach ($telemetryRaw as $item) {
                $nodeId = $item->node_id ?? 'unknown';
                $channel = $item->channel ?? 'default';
                
                if (!isset($latestTelemetryPerChannel[$channel])) {
                    $latestTelemetryPerChannel[$channel] = [];
                }
                if (!isset($latestTelemetryPerChannel[$channel][$nodeId])) {
                    $latestTelemetryPerChannel[$channel][$nodeId] = [];
                }
                
                $latestTelemetryPerChannel[$channel][$nodeId][] = [
                    'metric_type' => $item->metric_type,
                    'value' => $item->value,
                    'updated_at' => $item->updated_at?->toIso8601String(),
                ];
            }

            // Возвращаем атомарный snapshot с фиксированными server_ts и last_event_id
            // Важно: last_event_id всегда должен присутствовать в ответе для корректной работы E2E тестов
            return response()->json([
                'status' => 'ok',
                'data' => [
                    'snapshot_id' => $snapshotId,
                    'server_ts' => $serverTs,
                    'last_event_id' => (int)$lastEventId, // Курсор событий для catch-up (явно приводим к int)
                    'zone_id' => $zone->id,
                    'devices_online_state' => $devicesOnlineState, // Статусы устройств
                    'active_alerts' => $activeAlerts, // Активные алерты
                    'latest_telemetry_per_channel' => $latestTelemetryPerChannel, // Последняя телеметрия по каналам
                    'commands_recent' => $recentCommands, // Последние команды со статусами
                ],
            ]);
        });
    }

    /**
     * Получить события зоны (Zone Event Ledger).
     * 
     * GET /api/zones/{zone}/events?after_id=...&limit=...
     * 
     * Возвращает отсортированный список событий с поддержкой пагинации по after_id.
     * Используется для синхронизации клиентов, которые пропустили WebSocket события.
     */
    public function events(Request $request, Zone $zone): JsonResponse
    {
        $user = $request->user();
        if (!$user) {
            return response()->json([
                'status' => 'error',
                'message' => 'Unauthorized',
            ], 401);
        }

        if (!ZoneAccessHelper::canAccessZone($user, $zone)) {
            return response()->json([
                'status' => 'error',
                'message' => 'Forbidden: Access denied to this zone',
            ], 403);
        }

        // Преобразуем cycle_only в boolean до валидации (может быть строкой "true"/"false" или boolean)
        // Axios передает boolean как строку "true"/"false" в query параметрах
        $cycleOnlyInput = $request->query->get('cycle_only');
        if ($cycleOnlyInput !== null) {
            // Преобразуем строку "true"/"false" в boolean
            $boolValue = filter_var($cycleOnlyInput, FILTER_VALIDATE_BOOLEAN, FILTER_NULL_ON_FAILURE);
            if ($boolValue !== null) {
                // Заменяем значение в query параметрах
                $request->query->set('cycle_only', $boolValue);
            } else {
                // Если не удалось преобразовать, удаляем параметр
                $request->query->remove('cycle_only');
            }
        }
        
        // Валидация query параметров
        $validated = $request->validate([
            'after_id' => ['nullable', 'integer', 'min:0'],  // Разрешаем 0 для начального запроса
            'limit' => ['nullable', 'integer', 'min:1', 'max:1000'],
            'cycle_only' => ['nullable', 'boolean'], // Фильтр для событий цикла
        ]);

        $afterId = $validated['after_id'] ?? null;
        $limit = min($validated['limit'] ?? 50, 200); // Максимум 200 для E2E, по умолчанию 50
        $cycleOnly = $validated['cycle_only'] ?? false;

        // Запрос событий для зоны
        $query = DB::table('zone_events')
            ->where('zone_id', $zone->id);

        // Фильтр для событий цикла: старт, смена стадии, critical alerts, ручные вмешательства
        if ($cycleOnly) {
            $cycleEventTypes = [
                'CYCLE_CREATED',
                'CYCLE_STARTED',
                'CYCLE_PAUSED',
                'CYCLE_RESUMED',
                'CYCLE_HARVESTED',
                'CYCLE_ABORTED',
                'CYCLE_RECIPE_REBASED',
                'PHASE_TRANSITION',
                'RECIPE_PHASE_CHANGED',
                'ZONE_COMMAND', // Ручные вмешательства
            ];
            
            // Используем where с замыканием для правильной группировки условий
            $query->where(function ($q) use ($cycleEventTypes) {
                $q->whereIn('type', $cycleEventTypes);
            });
            
            // Также включаем critical alerts (ALERT_CREATED с severity CRITICAL)
            // Проверяем, какая колонка существует (payload_json или details) для обратной совместимости
            $hasPayloadJson = DB::getSchemaBuilder()->hasColumn('zone_events', 'payload_json');
            $detailsColumn = $hasPayloadJson ? 'payload_json' : 'details';
            
            $query->orWhere(function ($q) use ($detailsColumn) {
                $q->where('type', 'ALERT_CREATED')
                  ->whereRaw("{$detailsColumn}->>'severity' = 'CRITICAL'");
            });
        } else {
            // Определяем колонку details для случая, когда cycle_only = false
            $hasPayloadJson = DB::getSchemaBuilder()->hasColumn('zone_events', 'payload_json');
            $detailsColumn = $hasPayloadJson ? 'payload_json' : 'details';
        }

        // Убеждаемся, что $detailsColumn определена (если cycle_only = false, она еще не определена)
        if (!isset($detailsColumn)) {
            $hasPayloadJson = DB::getSchemaBuilder()->hasColumn('zone_events', 'payload_json');
            $detailsColumn = $hasPayloadJson ? 'payload_json' : 'details';
        }

        $query->orderBy('id', 'asc'); // Строго по возрастанию id для гарантии порядка

        // Если указан after_id, получаем события после этого ID
        if ($afterId) {
            $query->where('id', '>', $afterId);
        }
        
        $events = $query->limit($limit)->get([
            'id as event_id',
            'zone_id',
            'type',
            DB::raw("{$detailsColumn} as details"),
            'created_at',
        ])->map(function ($event) {
            // Преобразуем details из jsonb в массив, если это строка
            if (is_string($event->details)) {
                $event->details = json_decode($event->details, true) ?? [];
            }
            // Добавляем payload для обратной совместимости
            $event->payload = $event->details;
            return $event;
        });

        // Получаем последний event_id для следующего запроса
        $lastEventId = $events->isNotEmpty() ? $events->last()->event_id : $afterId;

        // Проверяем, есть ли еще события после последнего
        $hasMore = false;
        if ($lastEventId) {
            $hasMore = DB::table('zone_events')
                ->where('zone_id', $zone->id)
                ->where('id', '>', $lastEventId)
                ->exists();
        }

        return response()->json([
            'status' => 'ok',
            'data' => $events->values(),
            'last_event_id' => $lastEventId,
            'has_more' => $hasMore,
        ]);
    }

    /**
     * Обновить инфраструктуру зоны
     */
    public function updateInfrastructure(Request $request, Zone $zone): JsonResponse
    {
        $user = $request->user();
        if (!$user) {
            return response()->json(['status' => 'error', 'message' => 'Unauthorized'], 401);
        }

        if (!ZoneAccessHelper::canAccessZone($user, $zone)) {
            return response()->json(['status' => 'error', 'message' => 'Forbidden'], 403);
        }

        $data = $request->validate([
            'infrastructure' => ['required', 'array'],
            'infrastructure.*.asset_type' => ['required', 'string', 'in:PUMP,MISTER,TANK_NUTRIENT,TANK_CLEAN,DRAIN,LIGHT,VENT,HEATER'],
            'infrastructure.*.label' => ['required', 'string', 'max:255'],
            'infrastructure.*.required' => ['required', 'boolean'],
            'infrastructure.*.capacity_liters' => ['nullable', 'numeric', 'min:0'],
            'infrastructure.*.flow_rate' => ['nullable', 'numeric', 'min:0'],
            'infrastructure.*.specs' => ['nullable', 'array'],
        ]);

        return DB::transaction(function () use ($zone, $data) {
            // Удаляем старую инфраструктуру
            $zone->infrastructure()->delete();

            // Создаем новую
            foreach ($data['infrastructure'] as $assetData) {
                $zone->infrastructure()->create($assetData);
            }

            $zone->refresh();
            $zone->load('infrastructure');

            return response()->json([
                'status' => 'ok',
                'data' => [
                    'zone_id' => $zone->id,
                    'infrastructure' => $zone->infrastructure,
                ],
            ]);
        });
    }
}


