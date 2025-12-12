<?php

namespace App\Http\Controllers;

use App\Helpers\ZoneAccessHelper;
use App\Models\DeviceNode;
use App\Models\Greenhouse;
use App\Models\NodeChannel;
use App\Models\Plant;
use App\Models\Recipe;
use App\Models\Zone;
use App\Models\GrowCycle;
use App\Enums\GrowCycleStatus;
use App\Models\ZoneRecipeInstance;
use App\Services\ZoneService;
use Illuminate\Http\JsonResponse;
use Illuminate\Http\Request;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Log;
use Illuminate\Support\Facades\Validator;

class GrowCycleWizardController extends Controller
{
    public function __construct(
        private readonly ZoneService $zoneService
    ) {
    }

    /**
     * Получить данные для wizard (greenhouses, zones, nodes, plants, recipes)
     */
    public function getWizardData(Request $request): JsonResponse
    {
        $user = $request->user();
        if (!$user) {
            return response()->json(['status' => 'error', 'message' => 'Unauthorized'], 401);
        }

        // Получаем теплицы с зонами
        $greenhouses = Greenhouse::with(['zones' => function ($query) use ($user) {
            // Фильтруем зоны по доступу пользователя
            $zones = Zone::all()->filter(fn($zone) => ZoneAccessHelper::canAccessZone($user, $zone));
            $query->whereIn('id', $zones->pluck('id'));
        }])->get();

        // Получаем все доступные зоны
        $zones = Zone::all()->filter(fn($zone) => ZoneAccessHelper::canAccessZone($user, $zone))->values();

        // Получаем растения
        $plants = Plant::orderBy('name')->get();

        // Получаем рецепты
        $recipes = Recipe::with('phases')->orderBy('name')->get();

        return response()->json([
            'status' => 'ok',
            'data' => [
                'greenhouses' => $greenhouses->map(fn($gh) => [
                    'id' => $gh->id,
                    'uid' => $gh->uid,
                    'name' => $gh->name,
                    'zones' => $gh->zones->map(fn($zone) => [
                        'id' => $zone->id,
                        'uid' => $zone->uid,
                        'name' => $zone->name,
                        'status' => $zone->status,
                    ]),
                ]),
                'zones' => $zones->map(fn($zone) => [
                    'id' => $zone->id,
                    'uid' => $zone->uid,
                    'name' => $zone->name,
                    'status' => $zone->status,
                    'greenhouse_id' => $zone->greenhouse_id,
                    'nodes' => $zone->nodes()->with('channels')->get()->map(fn($node) => [
                        'id' => $node->id,
                        'uid' => $node->uid,
                        'name' => $node->name,
                        'type' => $node->type,
                        'status' => $node->status,
                        'last_seen_at' => $node->last_seen_at,
                        'channels' => $node->channels->map(fn($channel) => [
                            'id' => $channel->id,
                            'channel' => $channel->channel,
                            'type' => $channel->type,
                            'metric' => $channel->metric,
                        ]),
                    ]),
                ]),
                'plants' => $plants->map(fn($plant) => [
                    'id' => $plant->id,
                    'slug' => $plant->slug,
                    'name' => $plant->name,
                    'species' => $plant->species,
                    'variety' => $plant->variety,
                    'substrate_type' => $plant->substrate_type,
                    'growing_system' => $plant->growing_system,
                    'recommended_recipes' => $plant->recommended_recipes,
                ]),
                'recipes' => $recipes->map(fn($recipe) => [
                    'id' => $recipe->id,
                    'name' => $recipe->name,
                    'description' => $recipe->description,
                    'phases' => $recipe->phases->map(fn($phase) => [
                        'id' => $phase->id,
                        'phase_index' => $phase->phase_index,
                        'name' => $phase->name,
                        'duration_hours' => $phase->duration_hours,
                    ])->sortBy('phase_index')->values(),
                ]),
            ],
        ]);
    }

    /**
     * Получить данные зоны для wizard (nodes, channels, health)
     */
    public function getZoneData(Request $request, Zone $zone): JsonResponse
    {
        $user = $request->user();
        if (!$user) {
            return response()->json(['status' => 'error', 'message' => 'Unauthorized'], 401);
        }

        if (!ZoneAccessHelper::canAccessZone($user, $zone)) {
            return response()->json(['status' => 'error', 'message' => 'Forbidden'], 403);
        }

        $zone->load(['nodes.channels', 'greenhouse']);

        // Проверяем готовность зоны
        $readiness = $this->checkZoneReadiness($zone);

        return response()->json([
            'status' => 'ok',
            'data' => [
                'zone' => [
                    'id' => $zone->id,
                    'uid' => $zone->uid,
                    'name' => $zone->name,
                    'status' => $zone->status,
                    'health_score' => $zone->health_score,
                    'health_status' => $zone->health_status,
                    'greenhouse_id' => $zone->greenhouse_id,
                ],
                'nodes' => $zone->nodes->map(fn($node) => [
                    'id' => $node->id,
                    'uid' => $node->uid,
                    'name' => $node->name,
                    'type' => $node->type,
                    'status' => $node->status,
                    'last_seen_at' => $node->last_seen_at,
                    'is_online' => $node->status === 'online',
                    'channels' => $node->channels->map(fn($channel) => [
                        'id' => $channel->id,
                        'channel' => $channel->channel,
                        'type' => $channel->type,
                        'metric' => $channel->metric,
                        'unit' => $channel->unit,
                    ]),
                ]),
                'readiness' => $readiness,
            ],
        ]);
    }

    /**
     * Создать grow cycle через wizard
     */
    public function createGrowCycle(Request $request): JsonResponse
    {
        $user = $request->user();
        if (!$user) {
            return response()->json(['status' => 'error', 'message' => 'Unauthorized'], 401);
        }

        $validator = Validator::make($request->all(), [
            'greenhouse_id' => 'nullable|exists:greenhouses,id',
            'zone_id' => 'required|exists:zones,id',
            'plant_id' => 'required|exists:plants,id',
            'recipe_id' => 'required|exists:recipes,id',
            'planting_date' => 'required|date',
            'automation_start_date' => 'required|date|after_or_equal:planting_date',
            'batch' => 'required|array',
            'batch.quantity' => 'nullable|integer|min:1',
            'batch.density' => 'nullable|numeric|min:0',
            'batch.substrate' => 'nullable|string',
            'batch.system' => 'nullable|string',
            'channel_bindings' => 'required|array',
            'channel_bindings.*.node_id' => 'required|exists:nodes,id',
            'channel_bindings.*.channel_id' => 'required|exists:node_channels,id',
            'channel_bindings.*.role' => 'required|string|in:main_pump,drain,mist,light,vent,heater',
            'stage_map' => 'nullable|array',
        ]);

        if ($validator->fails()) {
            return response()->json([
                'status' => 'error',
                'message' => 'Validation failed',
                'errors' => $validator->errors(),
            ], 422);
        }

        $data = $validator->validated();
        $zone = Zone::findOrFail($data['zone_id']);

        if (!ZoneAccessHelper::canAccessZone($user, $zone)) {
            return response()->json(['status' => 'error', 'message' => 'Forbidden'], 403);
        }

        // Проверяем готовность зоны перед созданием цикла
        $readiness = $this->checkZoneReadiness($zone);
        $readinessErrors = [];
        
        if (!$readiness['ready']) {
            // Собираем детальные ошибки
            if (!$readiness['checks']['main_pump']) {
                $readinessErrors[] = 'Основная помпа не привязана к каналу';
            }
            if (!$readiness['checks']['drain']) {
                $readinessErrors[] = 'Дренаж не привязан к каналу';
            }
            if (!$readiness['checks']['online_nodes']) {
                $readinessErrors[] = 'Нет онлайн нод в зоне';
            }
            if ($readiness['nodes']['total'] === 0) {
                $readinessErrors[] = 'Нет привязанных нод в зоне';
            }
            
            return response()->json([
                'status' => 'error',
                'message' => 'Zone is not ready for cycle start',
                'readiness_errors' => $readinessErrors,
                'readiness' => $readiness,
            ], 422);
        }

        try {
            return DB::transaction(function () use ($data, $zone, $user) {
                // 1. Привязываем каналы к ролям (сохраняем в config канала)
                foreach ($data['channel_bindings'] as $binding) {
                    $channel = NodeChannel::findOrFail($binding['channel_id']);
                    $config = $channel->config ?? [];
                    $config['zone_role'] = $binding['role'];
                    $channel->update(['config' => $config]);
                }

                // 2. Привязываем растение к зоне (если еще не привязано)
                $plant = Plant::findOrFail($data['plant_id']);
                if (!DB::table('plant_zone')->where('zone_id', $zone->id)->where('plant_id', $plant->id)->exists()) {
                    DB::table('plant_zone')->insert([
                        'plant_id' => $plant->id,
                        'zone_id' => $zone->id,
                        'assigned_at' => now(),
                        'metadata' => json_encode([
                            'batch' => $data['batch'],
                            'created_via' => 'grow_cycle_wizard',
                        ]),
                        'created_at' => now(),
                        'updated_at' => now(),
                    ]);
                }

                // 3. Создаем ZoneRecipeInstance
                $recipeInstance = $this->zoneService->attachRecipe(
                    $zone,
                    $data['recipe_id'],
                    new \DateTime($data['automation_start_date'])
                );

                // 4. Создаем GrowCycle
                $recipe = Recipe::findOrFail($data['recipe_id']);
                $totalDurationHours = $recipe->phases()->sum('duration_hours');

                $plantingDate = new \DateTime($data['planting_date']);
                $automationStartDate = new \DateTime($data['automation_start_date']);
                $estimatedHarvestDate = (clone $plantingDate)->modify("+{$totalDurationHours} hours");

                $growCycle = GrowCycle::create([
                    'greenhouse_id' => $zone->greenhouse_id,
                    'zone_id' => $zone->id,
                    'plant_id' => $data['plant_id'],
                    'recipe_id' => $data['recipe_id'],
                    'zone_recipe_instance_id' => $recipeInstance->id,
                    'status' => GrowCycleStatus::RUNNING,
                    'started_at' => $plantingDate,
                    'recipe_started_at' => $automationStartDate,
                    'expected_harvest_at' => $estimatedHarvestDate,
                    'batch_label' => $data['batch']['quantity'] 
                        ? "Партия {$data['batch']['quantity']} шт."
                        : 'Партия',
                    'settings' => [
                        'batch' => $data['batch'],
                        'planting_date' => $data['planting_date'],
                        'automation_start_date' => $data['automation_start_date'],
                        'channel_bindings' => $data['channel_bindings'],
                        'stage_map' => $data['stage_map'] ?? null,
                    ],
                ]);

                // 5. Обновляем статус зоны на RUNNING
                $zone->update(['status' => 'RUNNING']);

                Log::info('Grow cycle created via wizard', [
                    'grow_cycle_id' => $growCycle->id,
                    'zone_id' => $zone->id,
                    'plant_id' => $data['plant_id'],
                    'recipe_id' => $data['recipe_id'],
                    'user_id' => $user->id,
                ]);

                return response()->json([
                    'status' => 'ok',
                    'data' => [
                        'grow_cycle_id' => $growCycle->id,
                        'zone_id' => $zone->id,
                        'recipe_instance_id' => $recipeInstance->id,
                        'zone_status' => $zone->status,
                    ],
                ]);
            });
        } catch (\Exception $e) {
            Log::error('Failed to create grow cycle', [
                'error' => $e->getMessage(),
                'trace' => $e->getTraceAsString(),
                'data' => $data,
            ]);

            return response()->json([
                'status' => 'error',
                'message' => $e->getMessage(),
            ], 500);
        }
    }

    /**
     * Проверить готовность зоны
     */
    private function checkZoneReadiness(Zone $zone): array
    {
        $requiredAssets = [
            'main_pump' => false,
            'drain' => false,
            'tank_clean' => false,
            'tank_nutrient' => false,
        ];

        $optionalAssets = [
            'light' => false,
            'vent' => false,
            'heater' => false,
            'mist' => false,
        ];

        $onlineNodes = 0;
        $totalNodes = $zone->nodes->count();

        // Проверяем каналы и их роли
        foreach ($zone->nodes as $node) {
            if ($node->status === 'online') {
                $onlineNodes++;
            }

            foreach ($node->channels as $channel) {
                $role = $channel->config['zone_role'] ?? null;
                if ($role) {
                    if (in_array($role, ['main_pump', 'drain', 'mist'])) {
                        $requiredAssets[$role] = true;
                    } elseif (in_array($role, ['light', 'vent', 'heater'])) {
                        $optionalAssets[$role] = true;
                    }
                }
            }
        }

        // Проверяем наличие инфраструктуры (если есть таблица zone_infrastructure)
        // Пока упрощенно - проверяем только каналы

        $allRequiredReady = $requiredAssets['main_pump'] && $requiredAssets['drain'];
        $hasOnlineNodes = $onlineNodes > 0;

        return [
            'ready' => $allRequiredReady && $hasOnlineNodes,
            'required_assets' => $requiredAssets,
            'optional_assets' => $optionalAssets,
            'nodes' => [
                'online' => $onlineNodes,
                'total' => $totalNodes,
                'all_online' => $onlineNodes === $totalNodes && $totalNodes > 0,
            ],
            'checks' => [
                'main_pump' => $requiredAssets['main_pump'],
                'drain' => $requiredAssets['drain'],
                'online_nodes' => $hasOnlineNodes,
            ],
        ];
    }
}

