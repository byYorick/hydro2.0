<?php

namespace App\Http\Controllers;

use App\Models\Zone;
use App\Services\ZoneService;
use Illuminate\Http\Request;
use Illuminate\Http\Response;

class ZoneController extends Controller
{
    public function __construct(
        private ZoneService $zoneService
    ) {
    }

    public function index(Request $request)
    {
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
        
        if (isset($validated['greenhouse_id'])) {
            $query->where('greenhouse_id', $validated['greenhouse_id']);
        }
        if (isset($validated['status'])) {
            $query->where('status', $validated['status']);
        }
        
        // Поиск по имени или описанию
        if (isset($validated['search']) && $validated['search']) {
            $searchTerm = '%' . strtolower($validated['search']) . '%';
            $query->where(function ($q) use ($searchTerm) {
                $q->whereRaw('LOWER(name) LIKE ?', [$searchTerm])
                  ->orWhereRaw('LOWER(description) LIKE ?', [$searchTerm]);
            });
        }
        
        $items = $query->latest('id')->paginate(25);
        return response()->json(['status' => 'ok', 'data' => $items]);
    }

    public function store(Request $request)
    {
        $data = $request->validate([
            'greenhouse_id' => ['nullable', 'integer', 'exists:greenhouses,id'],
            'preset_id' => ['nullable', 'integer', 'exists:presets,id'],
            'name' => ['required', 'string', 'max:255'],
            'description' => ['nullable', 'string'],
            'status' => ['nullable', 'string', 'max:32'],
        ]);
        $zone = $this->zoneService->create($data);
        return response()->json(['status' => 'ok', 'data' => $zone], Response::HTTP_CREATED);
    }

    public function show(Zone $zone)
    {
        $zone->load(['greenhouse', 'preset', 'nodes', 'recipeInstance.recipe.phases']);
        return response()->json(['status' => 'ok', 'data' => $zone]);
    }

    public function update(Request $request, Zone $zone)
    {
        $data = $request->validate([
            'greenhouse_id' => ['nullable', 'integer', 'exists:greenhouses,id'],
            'name' => ['sometimes', 'string', 'max:255'],
            'description' => ['nullable', 'string'],
            'status' => ['nullable', 'string', 'max:32'],
        ]);
        $zone = $this->zoneService->update($zone, $data);
        return response()->json(['status' => 'ok', 'data' => $zone]);
    }

    public function destroy(Zone $zone)
    {
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

    public function attachRecipe(Request $request, Zone $zone)
    {
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
            \Log::error('Failed to attach recipe', [
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

    public function changePhase(Request $request, Zone $zone)
    {
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

    public function nextPhase(Zone $zone)
    {
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

    public function pause(Zone $zone)
    {
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

    public function resume(Zone $zone)
    {
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

    public function health(Zone $zone)
    {
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

    public function fill(Request $request, Zone $zone)
    {
        $data = $request->validate([
            'target_level' => ['required', 'numeric', 'min:0.1', 'max:1.0'],
            'max_duration_sec' => ['nullable', 'integer', 'min:10', 'max:600'],
        ]);

        try {
            $result = $this->zoneService->fill($zone, $data);
            return response()->json(['status' => 'ok', 'data' => $result]);
        } catch (\DomainException $e) {
            return response()->json([
                'status' => 'error',
                'message' => $e->getMessage(),
            ], Response::HTTP_UNPROCESSABLE_ENTITY);
        }
    }

    public function drain(Request $request, Zone $zone)
    {
        $data = $request->validate([
            'target_level' => ['required', 'numeric', 'min:0.0', 'max:0.9'],
            'max_duration_sec' => ['nullable', 'integer', 'min:10', 'max:600'],
        ]);

        try {
            $result = $this->zoneService->drain($zone, $data);
            return response()->json(['status' => 'ok', 'data' => $result]);
        } catch (\DomainException $e) {
            return response()->json([
                'status' => 'error',
                'message' => $e->getMessage(),
            ], Response::HTTP_UNPROCESSABLE_ENTITY);
        }
    }

    public function calibrateFlow(Request $request, Zone $zone)
    {
        $data = $request->validate([
            'node_id' => ['required', 'integer', 'exists:nodes,id'],
            'channel' => ['required', 'string', 'max:128'],
            'pump_duration_sec' => ['nullable', 'integer', 'min:5', 'max:60'],
        ]);

        try {
            $result = $this->zoneService->calibrateFlow($zone, $data);
            return response()->json(['status' => 'ok', 'data' => $result]);
        } catch (\DomainException $e) {
            return response()->json([
                'status' => 'error',
                'message' => $e->getMessage(),
            ], Response::HTTP_UNPROCESSABLE_ENTITY);
        }
    }

    /**
     * Получить информацию о циклах зоны
     * GET /api/zones/{id}/cycles
     */
    public function cycles(Zone $zone)
    {
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


