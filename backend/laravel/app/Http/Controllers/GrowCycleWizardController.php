<?php

namespace App\Http\Controllers;

use App\Helpers\ZoneAccessHelper;
use App\Models\ChannelBinding;
use App\Models\DeviceNode;
use App\Models\Greenhouse;
use App\Models\InfrastructureInstance;
use App\Models\NodeChannel;
use App\Models\Plant;
use App\Models\Recipe;
use App\Models\Zone;
use App\Models\GrowCycle;
use App\Enums\GrowCycleStatus;
use App\Services\ZoneService;
use App\Services\GrowCycleService;
use App\Services\ZoneReadinessService;
use App\Models\RecipeRevision;
use Illuminate\Http\JsonResponse;
use Illuminate\Http\Request;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Log;
use Illuminate\Support\Facades\Validator;

class GrowCycleWizardController extends Controller
{
    private const WIZARD_BINDING_ROLES = [
        'main_pump',
        'drain',
        'mist',
        'light',
        'vent',
        'heater',
        'ph_acid_pump',
        'ph_base_pump',
        'ec_npk_pump',
        'ec_calcium_pump',
        'ec_magnesium_pump',
        'ec_micro_pump',
    ];

    public function __construct(
        private readonly ZoneService $zoneService,
        private readonly GrowCycleService $growCycleService,
        private readonly ZoneReadinessService $zoneReadinessService
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

        // Получаем рецепты с опубликованными ревизиями
        $recipes = Recipe::with(['publishedRevisions.phases'])->orderBy('name')->get();

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
                    'latest_published_revision_id' => $recipe->latestPublishedRevision?->id,
                    'published_revisions' => $recipe->publishedRevisions->map(fn($revision) => [
                        'id' => $revision->id,
                        'revision_number' => $revision->revision_number,
                        'description' => $revision->description,
                        'phases' => $revision->phases->map(fn($phase) => [
                            'id' => $phase->id,
                            'phase_index' => $phase->phase_index,
                            'name' => $phase->name,
                            'duration_hours' => $phase->duration_hours,
                            'duration_days' => $phase->duration_days,
                            'ph_target' => $phase->ph_target,
                            'ph_min' => $phase->ph_min,
                            'ph_max' => $phase->ph_max,
                            'ec_target' => $phase->ec_target,
                            'ec_min' => $phase->ec_min,
                            'ec_max' => $phase->ec_max,
                            'irrigation_interval_sec' => $phase->irrigation_interval_sec,
                            'temp_air_target' => $phase->temp_air_target,
                            'humidity_target' => $phase->humidity_target,
                            'co2_target' => $phase->co2_target,
                        ])->sortBy('phase_index')->values(),
                    ])->values(),
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
            'recipe_revision_id' => 'required|exists:recipe_revisions,id',
            'planting_date' => 'required|date',
            'automation_start_date' => 'required|date|after_or_equal:planting_date',
            'batch' => 'required|array',
            'batch.quantity' => 'nullable|integer|min:1',
            'batch.density' => 'nullable|numeric|min:0',
            'batch.substrate' => 'nullable|string',
            'batch.system' => 'nullable|string',
            'channel_bindings' => 'required|array',
            'channel_bindings.*.node_id' => 'required|exists:nodes,id',
            'channel_bindings.*.channel_id' => 'required|distinct|exists:node_channels,id',
            'channel_bindings.*.role' => 'required|string|distinct|in:'.implode(',', self::WIZARD_BINDING_ROLES),
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

        try {
            return DB::transaction(function () use ($data, $zone, $user) {
                // 1. Привязываем каналы к ролям в нормализованной инфраструктуре.
                $this->persistChannelBindings($zone, $data['channel_bindings']);

                // 2. Проверяем готовность зоны после применения bind-ов.
                $readiness = $this->checkZoneReadiness($zone->fresh());
                $readinessErrors = $this->buildZoneReadinessErrors($readiness);
                if (! $readiness['ready']) {
                    return response()->json([
                        'status' => 'error',
                        'message' => 'Zone is not ready for cycle start',
                        'readiness_errors' => $readinessErrors,
                        'readiness' => $readiness,
                    ], 422);
                }

                // 3. Привязываем растение к зоне (если еще не привязано)
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

                // 4. Получаем ревизию рецепта (должна быть опубликована)
                $revision = RecipeRevision::findOrFail($data['recipe_revision_id']);
                if ($revision->status !== 'PUBLISHED') {
                    throw new \DomainException('Only PUBLISHED revisions can be used for new cycles');
                }

                // 5. Создаем GrowCycle через GrowCycleService
                $plantingDate = new \DateTime($data['planting_date']);
                $automationStartDate = new \DateTime($data['automation_start_date']);
                
                $growCycle = $this->growCycleService->createCycle(
                    $zone,
                    $revision,
                    $data['plant_id'],
                    [
                        'planting_at' => $plantingDate->format('Y-m-d H:i:s'),
                        'start_immediately' => $automationStartDate <= $plantingDate,
                        'batch_label' => $data['batch']['quantity'] 
                            ? "Партия {$data['batch']['quantity']} шт."
                            : 'Партия',
                        'notes' => json_encode([
                            'batch' => $data['batch'],
                            'planting_date' => $data['planting_date'],
                            'automation_start_date' => $data['automation_start_date'],
                            'channel_bindings' => $data['channel_bindings'],
                            'stage_map' => $data['stage_map'] ?? null,
                        ]),
                    ],
                    $user->id
                );

                // 6. Обновляем статус зоны на RUNNING
                $zone->update(['status' => 'RUNNING']);

                Log::info('Grow cycle created via wizard', [
                    'grow_cycle_id' => $growCycle->id,
                    'zone_id' => $zone->id,
                    'plant_id' => $data['plant_id'],
                    'recipe_revision_id' => $revision->id,
                    'user_id' => $user->id,
                ]);

                return response()->json([
                    'status' => 'ok',
                    'data' => [
                        'grow_cycle_id' => $growCycle->id,
                        'zone_id' => $zone->id,
                        'recipe_revision_id' => $revision->id,
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
        return $this->zoneReadinessService->checkZoneReadiness($zone);
    }

    private function buildZoneReadinessErrors(array $readiness): array
    {
        $errors = [];
        $checks = is_array($readiness['checks'] ?? null) ? $readiness['checks'] : [];

        if (! ($checks['has_nodes'] ?? false)) {
            $errors[] = 'Нет привязанных нод в зоне';
        }
        if (! ($checks['online_nodes'] ?? false)) {
            $errors[] = 'Нет онлайн нод в зоне';
        }

        $roleMessages = [
            'main_pump' => 'Основная помпа не привязана к каналу',
            'drain' => 'Дренаж не привязан к каналу',
            'ph_acid_pump' => 'Насос pH кислоты не привязан к каналу',
            'ph_base_pump' => 'Насос pH щёлочи не привязан к каналу',
            'ec_npk_pump' => 'Насос EC NPK не привязан к каналу',
            'ec_calcium_pump' => 'Насос EC Calcium не привязан к каналу',
            'ec_magnesium_pump' => 'Насос EC Magnesium не привязан к каналу',
            'ec_micro_pump' => 'Насос EC Micro не привязан к каналу',
        ];
        foreach ($roleMessages as $role => $message) {
            if (array_key_exists($role, $checks) && ! $checks[$role]) {
                $errors[] = $message;
            }
        }

        foreach ($readiness['errors'] ?? [] as $issue) {
            if (is_array($issue) && isset($issue['message']) && is_string($issue['message'])) {
                $errors[] = $issue['message'];
            } elseif (is_string($issue)) {
                $errors[] = $issue;
            }
        }

        return array_values(array_unique($errors));
    }

    /**
     * Сохранить channel bindings в нормализованной модели инфраструктуры.
     *
     * @param  array<int, array{node_id:int, channel_id:int, role:string}>  $bindings
     */
    private function persistChannelBindings(Zone $zone, array $bindings): void
    {
        $channelIds = array_values(array_unique(array_map(
            static fn (array $binding): int => (int) $binding['channel_id'],
            $bindings
        )));

        $channels = NodeChannel::query()
            ->with('node:id,zone_id')
            ->whereIn('id', $channelIds)
            ->get()
            ->keyBy('id');

        foreach ($bindings as $binding) {
            $channelId = (int) $binding['channel_id'];
            $expectedNodeId = (int) $binding['node_id'];
            $role = (string) $binding['role'];

            /** @var NodeChannel|null $channel */
            $channel = $channels->get($channelId);
            if (! $channel) {
                throw new \DomainException("Channel {$channelId} not found");
            }

            if ((int) $channel->node_id !== $expectedNodeId) {
                throw new \DomainException("Channel {$channelId} does not belong to node {$expectedNodeId}");
            }

            $channelZoneId = (int) ($channel->node?->zone_id ?? 0);
            if ($channelZoneId !== (int) $zone->id) {
                throw new \DomainException("Channel {$channelId} does not belong to zone {$zone->id}");
            }

            $meta = $this->bindingRoleMeta($role);
            $instance = InfrastructureInstance::query()->firstOrCreate(
                [
                    'owner_type' => 'zone',
                    'owner_id' => $zone->id,
                    'label' => $meta['label'],
                ],
                [
                    'asset_type' => $meta['asset_type'],
                    'required' => $meta['required'],
                ]
            );

            if ($instance->asset_type !== $meta['asset_type'] || (bool) $instance->required !== $meta['required']) {
                $instance->asset_type = $meta['asset_type'];
                $instance->required = $meta['required'];
                $instance->save();
            }

            ChannelBinding::query()->updateOrCreate(
                ['node_channel_id' => $channel->id],
                [
                    'infrastructure_instance_id' => $instance->id,
                    'direction' => 'actuator',
                    'role' => $role,
                ]
            );
        }
    }

    /**
     * @return array{label:string, asset_type:string, required:bool}
     */
    private function bindingRoleMeta(string $role): array
    {
        return match ($role) {
            'main_pump' => ['label' => 'Основная помпа', 'asset_type' => 'PUMP', 'required' => true],
            'drain' => ['label' => 'Дренаж', 'asset_type' => 'PUMP', 'required' => true],
            'mist' => ['label' => 'Туман', 'asset_type' => 'MIST', 'required' => false],
            'light' => ['label' => 'Освещение', 'asset_type' => 'LIGHT', 'required' => false],
            'vent' => ['label' => 'Вентиляция', 'asset_type' => 'FAN', 'required' => false],
            'heater' => ['label' => 'Отопление', 'asset_type' => 'HEATER', 'required' => false],
            'ph_acid_pump' => ['label' => 'Насос pH кислоты', 'asset_type' => 'PUMP', 'required' => true],
            'ph_base_pump' => ['label' => 'Насос pH щёлочи', 'asset_type' => 'PUMP', 'required' => true],
            'ec_npk_pump' => ['label' => 'Насос EC NPK', 'asset_type' => 'PUMP', 'required' => true],
            'ec_calcium_pump' => ['label' => 'Насос EC Calcium', 'asset_type' => 'PUMP', 'required' => true],
            'ec_magnesium_pump' => ['label' => 'Насос EC Magnesium', 'asset_type' => 'PUMP', 'required' => true],
            'ec_micro_pump' => ['label' => 'Насос EC Micro', 'asset_type' => 'PUMP', 'required' => true],
            default => ['label' => $role, 'asset_type' => 'PUMP', 'required' => false],
        };
    }
}
