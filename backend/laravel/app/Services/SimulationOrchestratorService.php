<?php

namespace App\Services;

use App\Enums\GrowCycleStatus;
use App\Enums\NodeLifecycleState;
use App\Models\ChannelBinding;
use App\Models\DeviceNode;
use App\Models\GrowCycle;
use App\Models\InfrastructureInstance;
use App\Models\NodeChannel;
use App\Models\Plant;
use App\Models\Recipe;
use App\Models\RecipeRevision;
use App\Models\RecipeRevisionPhase;
use App\Models\SimulationReport;
use App\Models\Zone;
use App\Models\ZoneSimulation;
use App\Models\User;
use Illuminate\Database\Eloquent\Collection as EloquentCollection;
use Illuminate\Support\Carbon;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Log;
use Illuminate\Support\Str;

class SimulationOrchestratorService
{
    public function __construct(
        private GrowCycleService $growCycleService,
    ) {}

    /**
     * Создать отдельную сим-зону и grow-cycle для live симуляции.
     *
     * @param array{full_simulation?: bool} $options
     * @return array{zone: Zone, grow_cycle: \App\Models\GrowCycle, plant?: Plant|null, recipe?: Recipe|null, recipe_revision?: RecipeRevision|null, node?: DeviceNode|null}
     */
    public function createSimulationContext(Zone $sourceZone, ?int $recipeId, array $options = []): array
    {
        $context = DB::transaction(function () use ($sourceZone, $recipeId, $options): array {
            $fullSimulation = (bool) ($options['full_simulation'] ?? false);
            $createdPlant = null;
            $createdRecipe = null;
            $createdRevision = null;
            $createdNode = null;

            if ($fullSimulation) {
                [$createdPlant, $createdRecipe, $createdRevision] = $this->createSimulationRecipeBundle();
                $recipeId = $createdRecipe->id;
            }

            if (! $recipeId) {
                throw new \RuntimeException('recipe_id required for live simulation context.');
            }

            $simZone = Zone::create([
                'uid' => 'sim-' . Str::uuid()->toString(),
                'greenhouse_id' => $sourceZone->greenhouse_id,
                'preset_id' => $sourceZone->preset_id,
                'name' => 'SIM ' . ($sourceZone->name ?: ('Zone ' . $sourceZone->id)),
                'description' => $sourceZone->description,
                'status' => 'RUNNING',
                'health_score' => $sourceZone->health_score,
                'health_status' => $sourceZone->health_status,
                'hardware_profile' => $sourceZone->hardware_profile,
                'capabilities' => $this->buildSimulationCapabilities($sourceZone, $fullSimulation),
                'water_state' => $sourceZone->water_state,
                'solution_started_at' => $sourceZone->solution_started_at,
                'settings' => $this->buildSimulationSettings($sourceZone),
            ]);

            $channelMap = $this->cloneNodesAndChannels($sourceZone, $simZone);
            $this->cloneInfrastructure($sourceZone, $simZone, $channelMap);

            $createdNode = $this->ensureSimulationRuntimeInfrastructure($simZone);
            $this->ensureSimulationDosingInfrastructure($simZone, $createdNode);
            $this->syncSimulationZoneAutomationConfig($sourceZone, $simZone);

            $cycle = $this->createSimulationGrowCycle(
                $sourceZone,
                $simZone,
                $recipeId,
                $createdPlant?->id
            );

            Log::info('Simulation context created', [
                'source_zone_id' => $sourceZone->id,
                'simulation_zone_id' => $simZone->id,
                'grow_cycle_id' => $cycle->id,
            ]);

            return [
                'zone' => $simZone->fresh(),
                'grow_cycle' => $cycle->fresh(),
                'plant' => $createdPlant?->fresh(),
                'recipe' => $createdRecipe?->fresh(),
                'recipe_revision' => $createdRevision?->fresh(),
                'node' => $createdNode?->fresh(),
            ];
        });

        $growCycle = $context['grow_cycle'] ?? null;
        if ($growCycle instanceof GrowCycle) {
            $context['grow_cycle'] = $this->startSimulationGrowCycleAfterCommit($growCycle);
        }

        return $context;
    }

    private function startSimulationGrowCycleAfterCommit(GrowCycle $cycle): GrowCycle
    {
        $freshCycle = GrowCycle::query()->findOrFail($cycle->id);

        if ($freshCycle->status === GrowCycleStatus::PLANNED) {
            return $this->growCycleService->startCycle($freshCycle);
        }

        return $freshCycle->fresh();
    }

    private function syncSimulationZoneAutomationConfig(Zone $sourceZone, Zone $simZone): void
    {
        /** @var AutomationConfigDocumentService $documents */
        $documents = app(AutomationConfigDocumentService::class);
        /** @var AutomationConfigRegistry $registry */
        $registry = app(AutomationConfigRegistry::class);

        foreach ($registry->requiredNamespacesForScope(AutomationConfigRegistry::SCOPE_ZONE) as $namespace) {
            if ($namespace === AutomationConfigRegistry::NAMESPACE_ZONE_LOGIC_PROFILE) {
                continue;
            }

            $payload = $documents->getPayload(
                $namespace,
                AutomationConfigRegistry::SCOPE_ZONE,
                (int) $sourceZone->id,
                false
            );

            if ($payload === []) {
                $payload = $registry->defaultPayload($namespace);
            }

            $documents->upsertDocument(
                $namespace,
                AutomationConfigRegistry::SCOPE_ZONE,
                (int) $simZone->id,
                $payload,
                null,
                'simulation_clone'
            );
        }

        $this->syncSimulationZoneLogicProfile($sourceZone, $simZone);
    }

    private function syncSimulationZoneLogicProfile(Zone $sourceZone, Zone $simZone): void
    {
        /** @var AutomationConfigDocumentService $documents */
        $documents = app(AutomationConfigDocumentService::class);
        $payload = $documents->getPayload(
            AutomationConfigRegistry::NAMESPACE_ZONE_LOGIC_PROFILE,
            AutomationConfigRegistry::SCOPE_ZONE,
            (int) $sourceZone->id,
            false
        );
        $normalizedPayload = $this->normalizeSimulationZoneLogicProfile($payload);
        $activeMode = $normalizedPayload['active_mode'] ?? null;
        $profiles = is_array($normalizedPayload['profiles'] ?? null) && ! array_is_list($normalizedPayload['profiles'])
            ? $normalizedPayload['profiles']
            : [];
        $activeProfile = is_string($activeMode) && is_array($profiles[$activeMode] ?? null) && ! array_is_list($profiles[$activeMode])
            ? $profiles[$activeMode]
            : null;
        $commandPlans = is_array($activeProfile['command_plans'] ?? null) && ! array_is_list($activeProfile['command_plans'])
            ? $activeProfile['command_plans']
            : [];

        if ($commandPlans !== []) {
            $documents->upsertDocument(
                AutomationConfigRegistry::NAMESPACE_ZONE_LOGIC_PROFILE,
                AutomationConfigRegistry::SCOPE_ZONE,
                (int) $simZone->id,
                $normalizedPayload,
                null,
                'simulation_clone'
            );

            return;
        }

        $subsystems = is_array($activeProfile['subsystems'] ?? null) && ! array_is_list($activeProfile['subsystems'])
            ? $activeProfile['subsystems']
            : [];

        app(ZoneLogicProfileService::class)->upsertProfile(
            zone: $simZone,
            mode: is_string($activeMode) && $activeMode !== '' ? $activeMode : ZoneLogicProfileCatalog::MODE_WORKING,
            subsystems: $this->buildSimulationFallbackSubsystems($subsystems),
            activate: true,
            userId: null,
        );
    }

    /**
     * @param  array<string, mixed>  $payload
     * @return array<string, mixed>
     */
    private function normalizeSimulationZoneLogicProfile(array $payload): array
    {
        $profiles = is_array($payload['profiles'] ?? null) && ! array_is_list($payload['profiles'])
            ? $payload['profiles']
            : [];
        $activeMode = is_string($payload['active_mode'] ?? null) && $payload['active_mode'] !== ''
            ? $payload['active_mode']
            : null;

        if (
            $activeMode === null
            || ! isset($profiles[$activeMode])
            || ! is_array($profiles[$activeMode])
            || array_is_list($profiles[$activeMode])
        ) {
            $activeMode = ZoneLogicProfileCatalog::MODE_WORKING;
            $workingProfile = $profiles[$activeMode] ?? [];
            $workingProfile = is_array($workingProfile) && ! array_is_list($workingProfile) ? $workingProfile : [];
            $profiles[$activeMode] = array_merge(
                $workingProfile,
                [
                    'mode' => $activeMode,
                    'is_active' => true,
                    'subsystems' => is_array($workingProfile['subsystems'] ?? null) && ! array_is_list($workingProfile['subsystems'])
                        ? $workingProfile['subsystems']
                        : [],
                ]
            );
        }

        foreach ($profiles as $mode => $profile) {
            if (! is_array($profile) || array_is_list($profile)) {
                continue;
            }

            $profiles[$mode] = array_merge(
                $profile,
                [
                    'mode' => $profile['mode'] ?? $mode,
                    'is_active' => $mode === $activeMode,
                ]
            );
        }

        return [
            'active_mode' => $activeMode,
            'profiles' => $profiles,
        ];
    }

    /**
     * @param  array<string, mixed>  $subsystems
     * @return array<string, mixed>
     */
    private function buildSimulationFallbackSubsystems(array $subsystems): array
    {
        /** @var AutomationConfigDocumentService $documents */
        $documents = app(AutomationConfigDocumentService::class);
        $commandTemplates = $documents->getPayload(
            AutomationConfigRegistry::NAMESPACE_SYSTEM_COMMAND_TEMPLATES,
            AutomationConfigRegistry::SCOPE_SYSTEM,
            0,
            true
        );
        $automationDefaults = $documents->getPayload(
            AutomationConfigRegistry::NAMESPACE_SYSTEM_AUTOMATION_DEFAULTS,
            AutomationConfigRegistry::SCOPE_SYSTEM,
            0,
            true
        );

        $diagnostics = is_array($subsystems['diagnostics'] ?? null) && ! array_is_list($subsystems['diagnostics'])
            ? $subsystems['diagnostics']
            : [];
        $diagnosticsExecution = is_array($diagnostics['execution'] ?? null) && ! array_is_list($diagnostics['execution'])
            ? $diagnostics['execution']
            : [];
        if (
            ! is_array($diagnosticsExecution['two_tank_commands'] ?? null)
            || array_is_list($diagnosticsExecution['two_tank_commands'])
            || $diagnosticsExecution['two_tank_commands'] === []
        ) {
            $diagnosticsExecution['two_tank_commands'] = $commandTemplates;
        }
        $diagnosticsExecution['workflow'] = is_string($diagnosticsExecution['workflow'] ?? null) && $diagnosticsExecution['workflow'] !== ''
            ? $diagnosticsExecution['workflow']
            : 'cycle_start';
        $diagnosticsExecution['topology'] = is_string($diagnosticsExecution['topology'] ?? null) && $diagnosticsExecution['topology'] !== ''
            ? $diagnosticsExecution['topology']
            : 'two_tank_drip_substrate_trays';
        $diagnostics['enabled'] = (bool) ($diagnostics['enabled'] ?? true);
        $diagnostics['execution'] = $diagnosticsExecution;
        $subsystems['diagnostics'] = $diagnostics;

        $irrigation = is_array($subsystems['irrigation'] ?? null) && ! array_is_list($subsystems['irrigation'])
            ? $subsystems['irrigation']
            : [];
        $irrigationExecution = is_array($irrigation['execution'] ?? null) && ! array_is_list($irrigation['execution'])
            ? $irrigation['execution']
            : [];
        $irrigationExecution['system_type'] = is_string($irrigationExecution['system_type'] ?? null) && $irrigationExecution['system_type'] !== ''
            ? $irrigationExecution['system_type']
            : (string) ($automationDefaults['water_system_type'] ?? 'drip');
        $irrigationExecution['tanks_count'] = isset($irrigationExecution['tanks_count'])
            ? (int) $irrigationExecution['tanks_count']
            : (int) ($automationDefaults['water_tanks_count'] ?? 2);
        $irrigation['enabled'] = (bool) ($irrigation['enabled'] ?? true);
        $irrigation['execution'] = $irrigationExecution;
        $subsystems['irrigation'] = $irrigation;

        return $subsystems;
    }

    private function buildSimulationSettings(Zone $sourceZone): array
    {
        $settings = $sourceZone->settings ?? [];
        $settings['simulation'] = array_merge(
            $settings['simulation'] ?? [],
            [
                'source_zone_id' => $sourceZone->id,
                'source_zone_uid' => $sourceZone->uid,
                'created_at' => now()->toIso8601String(),
            ]
        );

        return $settings;
    }

    private function buildSimulationCapabilities(Zone $sourceZone, bool $fullSimulation): array
    {
        $capabilities = $sourceZone->capabilities ?? [];
        if (! is_array($capabilities)) {
            $capabilities = [];
        }

        if ($fullSimulation) {
            $capabilities = array_merge($capabilities, [
                'ph_control' => true,
                'ec_control' => true,
                'climate_control' => true,
                'light_control' => true,
                'irrigation_control' => true,
            ]);
        }

        return $capabilities;
    }

    /**
     * @return array<int, int> map old node_channel_id -> new node_channel_id
     */
    private function cloneNodesAndChannels(Zone $sourceZone, Zone $simZone): array
    {
        $sourceZone->loadMissing('nodes.channels');
        $channelMap = [];

        foreach ($this->selectSimulationSourceNodes($sourceZone->nodes) as $node) {
            $newNode = DeviceNode::create([
                'zone_id' => $simZone->id,
                'uid' => 'sim-' . Str::uuid()->toString(),
                'name' => $node->name ? 'SIM ' . $node->name : null,
                'type' => $node->type,
                'fw_version' => $node->fw_version,
                'hardware_revision' => $node->hardware_revision,
                'hardware_id' => 'sim-' . Str::uuid()->toString(),
                'status' => 'online',
                'lifecycle_state' => NodeLifecycleState::ASSIGNED_TO_ZONE,
                'validated' => true,
                'config' => $node->config,
                'last_seen_at' => now(),
            ]);

            foreach ($node->channels as $channel) {
                $newChannel = NodeChannel::create([
                    'node_id' => $newNode->id,
                    'channel' => $channel->channel,
                    'type' => $channel->type,
                    'metric' => $channel->metric,
                    'unit' => $channel->unit,
                    'config' => $channel->config,
                    'last_seen_at' => now(),
                ]);
                $channelMap[$channel->id] = $newChannel->id;
            }
        }

        return $channelMap;
    }

    /**
     * @param  EloquentCollection<int, DeviceNode>  $nodes
     * @return EloquentCollection<int, DeviceNode>
     */
    private function selectSimulationSourceNodes(EloquentCollection $nodes): EloquentCollection
    {
        if ($nodes->isEmpty()) {
            return $nodes;
        }

        $preferredByType = [];

        foreach ($nodes->groupBy(fn (DeviceNode $node) => (string) $node->type) as $type => $typedNodes) {
            if (! is_string($type) || $type === '') {
                continue;
            }

            /** @var DeviceNode|null $preferredNode */
            $preferredNode = $typedNodes
                ->sort(function (DeviceNode $left, DeviceNode $right): int {
                    $leftScore = $this->scoreSimulationSourceNode($left);
                    $rightScore = $this->scoreSimulationSourceNode($right);

                    if ($leftScore === $rightScore) {
                        return $left->id <=> $right->id;
                    }

                    return $rightScore <=> $leftScore;
                })
                ->first();

            if ($preferredNode instanceof DeviceNode) {
                $preferredByType[(string) $type] = $preferredNode->id;
            }
        }

        return $nodes
            ->filter(function (DeviceNode $node) use ($preferredByType): bool {
                $type = (string) $node->type;

                return ($preferredByType[$type] ?? null) === $node->id;
            })
            ->sortBy('id')
            ->values();
    }

    private function scoreSimulationSourceNode(DeviceNode $node): int
    {
        $score = 0;
        $channels = $node->relationLoaded('channels')
            ? $node->channels
            : $node->channels()->get();
        $channelNames = $channels
            ->map(fn (NodeChannel $channel) => Str::lower((string) $channel->channel))
            ->filter(fn (string $channel) => $channel !== '')
            ->values();

        if ($node->status === 'online') {
            $score += 20;
        }

        if ((bool) $node->validated) {
            $score += 10;
        }

        $type = Str::lower((string) $node->type);
        $weights = match ($type) {
            'irrig' => [
                'pump_main' => 20,
                'valve_clean_fill' => 12,
                'valve_solution_fill' => 12,
                'valve_solution_supply' => 12,
                'valve_irrigation' => 12,
                'level_clean_min' => 6,
                'level_clean_max' => 6,
                'level_solution_min' => 6,
                'level_solution_max' => 6,
            ],
            'ph' => [
                'system' => 20,
                'ph_sensor' => 12,
                'pump_acid' => 10,
                'pump_base' => 10,
            ],
            'ec' => [
                'system' => 20,
                'ec_sensor' => 12,
                'pump_a' => 8,
                'pump_b' => 8,
                'pump_c' => 8,
                'pump_d' => 8,
            ],
            default => [],
        };

        foreach ($weights as $channelName => $weight) {
            if ($channelNames->contains($channelName)) {
                $score += $weight;
            }
        }

        return $score;
    }

    private function cloneInfrastructure(Zone $sourceZone, Zone $simZone, array $channelMap): void
    {
        $instances = InfrastructureInstance::query()
            ->where('owner_type', 'zone')
            ->where('owner_id', $sourceZone->id)
            ->get();

        foreach ($instances as $instance) {
            $newInstance = InfrastructureInstance::create([
                'owner_type' => 'zone',
                'owner_id' => $simZone->id,
                'asset_type' => $instance->asset_type,
                'label' => $instance->label,
                'required' => $instance->required,
                'capacity_liters' => $instance->capacity_liters,
                'flow_rate' => $instance->flow_rate,
                'specs' => $instance->specs,
            ]);

            $bindings = ChannelBinding::query()
                ->where('infrastructure_instance_id', $instance->id)
                ->get();

            foreach ($bindings as $binding) {
                $newChannelId = $channelMap[$binding->node_channel_id] ?? null;
                if (! $newChannelId) {
                    continue;
                }
                ChannelBinding::updateOrCreate(
                    ['node_channel_id' => $newChannelId],
                    [
                        'infrastructure_instance_id' => $newInstance->id,
                        'direction' => $binding->direction,
                        'role' => $binding->role,
                    ]
                );
            }
        }
    }

    private function createSimulationGrowCycle(Zone $sourceZone, Zone $simZone, int $recipeId, ?int $plantId = null)
    {
        $revision = RecipeRevision::query()
            ->where('recipe_id', $recipeId)
            ->where('status', 'PUBLISHED')
            ->orderByDesc('revision_number')
            ->first();

        if (! $revision) {
            throw new \RuntimeException('Published recipe revision not found for simulation.');
        }

        if ($plantId) {
            return $this->createCycleWithPlant($sourceZone, $simZone, $revision, $plantId);
        }

        $plantId = $sourceZone->activeGrowCycle?->plant_id;
        if (! $plantId) {
            $plantId = Plant::query()->orderBy('id')->value('id');
        }
        if (! $plantId) {
            throw new \RuntimeException('No plants available to create simulation grow cycle.');
        }

        return $this->createCycleWithPlant($sourceZone, $simZone, $revision, (int) $plantId);
    }

    private function createCycleWithPlant(Zone $sourceZone, Zone $simZone, RecipeRevision $revision, int $plantId)
    {
        $cycle = $this->growCycleService->createCycle(
            $simZone,
            $revision,
            $plantId,
            [
                'start_immediately' => false,
                'notes' => 'Simulation cycle',
                'batch_label' => 'SIM',
            ],
            null
        );
        $this->growCycleService->syncCycleConfigDocuments($cycle->fresh(), [], null);
        $cycle->refresh();

        $cycleSettings = $cycle->settings ?? [];
        $cycleSettings['simulation'] = [
            'source_zone_id' => $sourceZone->id,
        ];
        $cycle->update(['settings' => $cycleSettings]);

        return $cycle->fresh();
    }

    /**
     * Создать растение + рецепт + ревизию с фазами для полной симуляции.
     *
     * @return array{0: Plant, 1: Recipe, 2: RecipeRevision}
     */
    private function createSimulationRecipeBundle(): array
    {
        $suffix = Str::uuid()->toString();
        $plant = Plant::create([
            'slug' => 'sim-' . $suffix,
            'name' => 'SIM Plant ' . $suffix,
            'species' => 'Simulation Plant',
        ]);

        $recipe = Recipe::create([
            'name' => 'SIM Recipe ' . $suffix,
            'description' => 'Simulation recipe for full cycle',
        ]);
        $recipe->plants()->sync([$plant->id]);

        $revision = RecipeRevision::create([
            'recipe_id' => $recipe->id,
            'revision_number' => 1,
            'status' => 'DRAFT',
            'description' => 'Simulation revision',
            'created_by' => null,
        ]);

        $phases = [
            [
                'phase_index' => 0,
                'name' => 'Старт',
                'duration_hours' => 1,
                'ph_target' => 6.0,
                'ec_target' => 1.4,
                'irrigation_mode' => 'SUBSTRATE',
            ],
            [
                'phase_index' => 1,
                'name' => 'Рост',
                'duration_hours' => 1,
                'ph_target' => 6.1,
                'ec_target' => 1.6,
                'irrigation_mode' => 'SUBSTRATE',
            ],
            [
                'phase_index' => 2,
                'name' => 'Финиш',
                'duration_hours' => 1,
                'ph_target' => 6.2,
                'ec_target' => 1.8,
                'irrigation_mode' => 'SUBSTRATE',
            ],
        ];

        foreach ($phases as $phase) {
            RecipeRevisionPhase::create(array_merge($phase, [
                'recipe_revision_id' => $revision->id,
            ]));
        }

        $revision->update([
            'status' => 'PUBLISHED',
            'published_at' => now(),
        ]);

        return [$plant, $recipe, $revision];
    }

    private function ensureSimulationRuntimeInfrastructure(Zone $simZone): DeviceNode
    {
        $irrigNode = $this->resolveOrCreateSimulationNode($simZone, 'irrig', 'SIM Irrigation Node');
        $phNode = $this->resolveOrCreateSimulationNode($simZone, 'ph', 'SIM pH Node');
        $ecNode = $this->resolveOrCreateSimulationNode($simZone, 'ec', 'SIM EC Node');

        $this->ensureSimulationNodeChannels($irrigNode, [
            ['channel' => 'pump_main', 'type' => 'ACTUATOR', 'metric' => 'PUMP', 'unit' => '', 'config' => ['actuator_type' => 'PUMP']],
            ['channel' => 'drain_pump', 'type' => 'ACTUATOR', 'metric' => 'PUMP', 'unit' => '', 'config' => ['actuator_type' => 'PUMP']],
            ['channel' => 'valve_clean_fill', 'type' => 'ACTUATOR', 'metric' => 'RELAY', 'unit' => '', 'config' => ['relay_type' => 'NO', 'actuator_type' => 'RELAY']],
            ['channel' => 'valve_clean_supply', 'type' => 'ACTUATOR', 'metric' => 'RELAY', 'unit' => '', 'config' => ['relay_type' => 'NO', 'actuator_type' => 'RELAY']],
            ['channel' => 'valve_solution_fill', 'type' => 'ACTUATOR', 'metric' => 'RELAY', 'unit' => '', 'config' => ['relay_type' => 'NO', 'actuator_type' => 'RELAY']],
            ['channel' => 'valve_solution_supply', 'type' => 'ACTUATOR', 'metric' => 'RELAY', 'unit' => '', 'config' => ['relay_type' => 'NO', 'actuator_type' => 'RELAY']],
            ['channel' => 'valve_irrigation', 'type' => 'ACTUATOR', 'metric' => 'RELAY', 'unit' => '', 'config' => ['relay_type' => 'NO', 'actuator_type' => 'RELAY']],
            ['channel' => 'level_clean_min', 'type' => 'SENSOR', 'metric' => 'WATER_LEVEL', 'unit' => '', 'config' => ['poll_interval_ms' => 500]],
            ['channel' => 'level_clean_max', 'type' => 'SENSOR', 'metric' => 'WATER_LEVEL', 'unit' => '', 'config' => ['poll_interval_ms' => 500]],
            ['channel' => 'level_solution_min', 'type' => 'SENSOR', 'metric' => 'WATER_LEVEL', 'unit' => '', 'config' => ['poll_interval_ms' => 500]],
            ['channel' => 'level_solution_max', 'type' => 'SENSOR', 'metric' => 'WATER_LEVEL', 'unit' => '', 'config' => ['poll_interval_ms' => 500]],
            ['channel' => 'flow_present', 'type' => 'SENSOR', 'metric' => 'FLOW_RATE', 'unit' => '', 'config' => ['poll_interval_ms' => 500]],
            ['channel' => 'pump_bus_current', 'type' => 'SENSOR', 'metric' => 'PUMP_CURRENT', 'unit' => 'mA', 'config' => ['poll_interval_ms' => 500]],
        ]);
        $this->ensureSimulationNodeChannels($phNode, [
            ['channel' => 'system', 'type' => 'SERVICE', 'metric' => 'SERVICE', 'unit' => ''],
            ['channel' => 'ph_sensor', 'type' => 'SENSOR', 'metric' => 'PH', 'unit' => 'pH', 'config' => ['poll_interval_ms' => 500]],
            ['channel' => 'solution_temp_c', 'type' => 'SENSOR', 'metric' => 'TEMPERATURE', 'unit' => 'C', 'config' => ['poll_interval_ms' => 500]],
            ['channel' => 'air_temp_c', 'type' => 'SENSOR', 'metric' => 'TEMPERATURE', 'unit' => 'C', 'config' => ['poll_interval_ms' => 500]],
            ['channel' => 'air_rh', 'type' => 'SENSOR', 'metric' => 'HUMIDITY', 'unit' => '%', 'config' => ['poll_interval_ms' => 500]],
            ['channel' => 'pump_acid', 'type' => 'ACTUATOR', 'metric' => 'PUMP', 'unit' => '', 'config' => ['actuator_type' => 'PUMP', 'pump_calibration' => ['component' => 'ph_down']]],
            ['channel' => 'pump_base', 'type' => 'ACTUATOR', 'metric' => 'PUMP', 'unit' => '', 'config' => ['actuator_type' => 'PUMP', 'pump_calibration' => ['component' => 'ph_up']]],
        ]);
        $this->ensureSimulationNodeChannels($ecNode, [
            ['channel' => 'system', 'type' => 'SERVICE', 'metric' => 'SERVICE', 'unit' => ''],
            ['channel' => 'ec_sensor', 'type' => 'SENSOR', 'metric' => 'EC', 'unit' => 'mS/cm', 'config' => ['poll_interval_ms' => 500]],
            ['channel' => 'pump_a', 'type' => 'ACTUATOR', 'metric' => 'PUMP', 'unit' => '', 'config' => ['actuator_type' => 'PUMP', 'pump_calibration' => ['component' => 'npk']]],
            ['channel' => 'pump_b', 'type' => 'ACTUATOR', 'metric' => 'PUMP', 'unit' => '', 'config' => ['actuator_type' => 'PUMP', 'pump_calibration' => ['component' => 'calcium']]],
            ['channel' => 'pump_c', 'type' => 'ACTUATOR', 'metric' => 'PUMP', 'unit' => '', 'config' => ['actuator_type' => 'PUMP', 'pump_calibration' => ['component' => 'magnesium']]],
            ['channel' => 'pump_d', 'type' => 'ACTUATOR', 'metric' => 'PUMP', 'unit' => '', 'config' => ['actuator_type' => 'PUMP', 'pump_calibration' => ['component' => 'micro']]],
        ]);

        $this->upsertSimulationZoneBinding($simZone, $irrigNode, 'pump_main', 'PUMP', 'Основная помпа', 'main_pump');
        $this->upsertSimulationZoneBinding($simZone, $irrigNode, 'drain_pump', 'PUMP', 'Дренажная помпа', 'drain');
        $this->upsertSimulationZoneBinding($simZone, $irrigNode, 'valve_clean_fill', 'OTHER', 'Клапан clean fill', 'valve_clean_fill');
        $this->upsertSimulationZoneBinding($simZone, $irrigNode, 'valve_clean_supply', 'OTHER', 'Клапан clean supply', 'valve_clean_supply');
        $this->upsertSimulationZoneBinding($simZone, $irrigNode, 'valve_solution_fill', 'OTHER', 'Клапан solution fill', 'valve_solution_fill');
        $this->upsertSimulationZoneBinding($simZone, $irrigNode, 'valve_solution_supply', 'OTHER', 'Клапан solution supply', 'valve_solution_supply');
        $this->upsertSimulationZoneBinding($simZone, $irrigNode, 'valve_irrigation', 'OTHER', 'Клапан irrigation', 'valve_irrigation');

        return $irrigNode->fresh();
    }

    private function resolveOrCreateSimulationNode(Zone $simZone, string $type, string $name): DeviceNode
    {
        $node = DeviceNode::query()
            ->where('zone_id', $simZone->id)
            ->where('type', $type)
            ->orderBy('id')
            ->first();

        if ($node) {
            $config = is_array($node->config) ? $node->config : [];
            $config['source'] = 'simulation';
            $node->forceFill([
                'name' => $node->name ?: $name,
                'status' => 'online',
                'lifecycle_state' => NodeLifecycleState::ASSIGNED_TO_ZONE,
                'validated' => true,
                'config' => $config,
                'last_seen_at' => now(),
            ])->save();

            return $node->fresh();
        }

        return DeviceNode::create([
            'zone_id' => $simZone->id,
            'uid' => 'sim-node-' . Str::uuid()->toString(),
            'name' => $name,
            'type' => $type,
            'fw_version' => 'sim',
            'hardware_revision' => 'sim',
            'hardware_id' => 'sim-hw-' . Str::uuid()->toString(),
            'status' => 'online',
            'lifecycle_state' => NodeLifecycleState::ASSIGNED_TO_ZONE,
            'validated' => true,
            'config' => [
                'source' => 'simulation',
            ],
            'last_seen_at' => now(),
        ]);
    }

    /**
     * @param  array<int, array<string, mixed>>  $definitions
     */
    private function ensureSimulationNodeChannels(DeviceNode $node, array $definitions): void
    {
        foreach ($definitions as $definition) {
            $channelName = (string) ($definition['channel'] ?? '');
            if ($channelName === '') {
                continue;
            }

            $channel = NodeChannel::query()
                ->where('node_id', $node->id)
                ->where('channel', $channelName)
                ->first();

            $payload = [
                'type' => $definition['type'] ?? 'SENSOR',
                'metric' => $definition['metric'] ?? null,
                'unit' => $definition['unit'] ?? null,
                'config' => $definition['config'] ?? null,
                'is_active' => true,
                'last_seen_at' => now(),
            ];

            if ($channel) {
                $channel->forceFill($payload)->save();
                continue;
            }

            NodeChannel::create(array_merge($payload, [
                'node_id' => $node->id,
                'channel' => $channelName,
            ]));
        }
    }

    private function upsertSimulationZoneBinding(
        Zone $simZone,
        DeviceNode $node,
        string $channelName,
        string $assetType,
        string $label,
        string $role
    ): void {
        $nodeChannel = NodeChannel::query()
            ->where('node_id', $node->id)
            ->where('channel', $channelName)
            ->first();

        if (! $nodeChannel) {
            return;
        }

        $instance = InfrastructureInstance::firstOrCreate(
            [
                'owner_type' => 'zone',
                'owner_id' => $simZone->id,
                'label' => $label,
            ],
            [
                'asset_type' => $assetType,
                'required' => true,
            ],
        );

        ChannelBinding::updateOrCreate(
            ['node_channel_id' => $nodeChannel->id],
            [
                'infrastructure_instance_id' => $instance->id,
                'direction' => 'actuator',
                'role' => $role,
            ],
        );
    }

    private function ensureSimulationDosingInfrastructure(Zone $simZone, ?DeviceNode $preferredNode = null): void
    {
        $capabilities = $simZone->capabilities ?? [];
        $phControl = (bool) ($capabilities['ph_control'] ?? false);
        $ecControl = (bool) ($capabilities['ec_control'] ?? false);

        if (! $phControl && ! $ecControl) {
            return;
        }

        $existingRoles = ChannelBinding::query()
            ->join('infrastructure_instances as ii', 'ii.id', '=', 'channel_bindings.infrastructure_instance_id')
            ->where('ii.owner_type', 'zone')
            ->where('ii.owner_id', $simZone->id)
            ->pluck('channel_bindings.role')
            ->all();
        $existingRoleSet = array_fill_keys($existingRoles, true);

        $definitions = [
            'ph_acid_pump' => [
                'node_type' => 'ph',
                'channel' => 'pump_acid',
                'label' => 'Насос дозирования кислоты',
                'required' => true,
                'enabled' => $phControl,
                'calibration_component' => 'ph_down',
            ],
            'ph_base_pump' => [
                'node_type' => 'ph',
                'channel' => 'pump_base',
                'label' => 'Насос дозирования щёлочи',
                'required' => true,
                'enabled' => $phControl,
                'calibration_component' => 'ph_up',
            ],
            'ec_npk_pump' => [
                'node_type' => 'ec',
                'channel' => 'pump_a',
                'label' => 'Насос EC NPK',
                'required' => true,
                'enabled' => $ecControl,
                'calibration_component' => 'npk',
            ],
            'ec_calcium_pump' => [
                'node_type' => 'ec',
                'channel' => 'pump_b',
                'label' => 'Насос EC Calcium',
                'required' => true,
                'enabled' => $ecControl,
                'calibration_component' => 'calcium',
            ],
            'ec_magnesium_pump' => [
                'node_type' => 'ec',
                'channel' => 'pump_c',
                'label' => 'Насос EC Magnesium',
                'required' => true,
                'enabled' => $ecControl,
                'calibration_component' => 'magnesium',
            ],
            'ec_micro_pump' => [
                'node_type' => 'ec',
                'channel' => 'pump_d',
                'label' => 'Насос EC Micro',
                'required' => true,
                'enabled' => $ecControl,
                'calibration_component' => 'micro',
            ],
        ];

        foreach ($definitions as $role => $definition) {
            if (! $definition['enabled'] || isset($existingRoleSet[$role])) {
                continue;
            }

            $targetNode = $preferredNode && $preferredNode->type === $definition['node_type']
                ? $preferredNode->fresh()
                : $this->resolveOrCreateSimulationNode($simZone, (string) $definition['node_type'], 'SIM ' . strtoupper((string) $definition['node_type']) . ' Node');

            $nodeChannel = NodeChannel::query()
                ->where('node_id', $targetNode->id)
                ->where('channel', $definition['channel'])
                ->first();

            if (! $nodeChannel) {
                $nodeChannel = NodeChannel::create([
                    'node_id' => $targetNode->id,
                    'channel' => $definition['channel'],
                    'type' => 'ACTUATOR',
                    'metric' => 'PUMP',
                    'unit' => '',
                    'config' => [
                        'actuator_type' => 'PUMP',
                        'pump_calibration' => [
                            'component' => $definition['calibration_component'] ?? null,
                        ],
                    ],
                    'last_seen_at' => now(),
                ]);
            } elseif (! empty($definition['calibration_component'])) {
                $channelConfig = is_array($nodeChannel->config) ? $nodeChannel->config : [];
                $pumpCalibration = is_array($channelConfig['pump_calibration'] ?? null)
                    ? $channelConfig['pump_calibration']
                    : [];
                if (($pumpCalibration['component'] ?? null) !== $definition['calibration_component']) {
                    $pumpCalibration['component'] = $definition['calibration_component'];
                    $channelConfig['pump_calibration'] = $pumpCalibration;
                    $channelConfig['actuator_type'] = 'PUMP';
                    $nodeChannel->config = $channelConfig;
                    $nodeChannel->last_seen_at = now();
                    $nodeChannel->save();
                }
            }

            $instance = InfrastructureInstance::firstOrCreate(
                [
                    'owner_type' => 'zone',
                    'owner_id' => $simZone->id,
                    'label' => $definition['label'],
                ],
                [
                    'asset_type' => 'PUMP',
                    'required' => $definition['required'],
                ],
            );

            ChannelBinding::updateOrCreate(
                ['node_channel_id' => $nodeChannel->id],
                [
                    'infrastructure_instance_id' => $instance->id,
                    'direction' => 'actuator',
                    'role' => $role,
                ],
            );
        }
    }

    /**
     * Выполнить полный цикл симуляции и сформировать отчет.
     *
     * @param array{zone: Zone, grow_cycle: GrowCycle, plant?: Plant|null, recipe?: Recipe|null, recipe_revision?: RecipeRevision|null, node?: DeviceNode|null} $context
     */
    public function executeFullSimulation(ZoneSimulation $simulation, array $context): SimulationReport
    {
        $simZone = $context['zone'];
        $cycle = $context['grow_cycle'];
        $userId = $this->resolveSimulationUserId();

        $simMeta = [];
        $scenario = $simulation->scenario ?? [];
        if (is_array($scenario) && isset($scenario['simulation']) && is_array($scenario['simulation'])) {
            $simMeta = $scenario['simulation'];
        }

        $summary = [
            'source_zone_id' => $simMeta['source_zone_id'] ?? null,
            'simulation_zone_id' => $simZone->id,
            'simulation_grow_cycle_id' => $cycle->id,
            'created_plant_id' => $context['plant']?->id,
            'created_recipe_id' => $context['recipe']?->id,
            'created_recipe_revision_id' => $context['recipe_revision']?->id,
            'created_node_id' => $context['node']?->id,
            'created_node_uid' => $context['node']?->uid,
        ];

        $report = SimulationReport::updateOrCreate(
            ['simulation_id' => $simulation->id],
            [
                'zone_id' => $simZone->id,
                'status' => 'running',
                'started_at' => now(),
                'summary_json' => $summary,
                'phases_json' => [],
                'metrics_json' => null,
                'errors_json' => null,
            ]
        );

        $this->recordSimulationEvent(
            $simulation->id,
            $simZone->id,
            'laravel',
            'report',
            'running',
            'Старт полного цикла симуляции',
            ['report_id' => $report->id]
        );

        $phasesReport = [];
        $cycle = $cycle->fresh(['currentPhase', 'recipeRevision.phases']);
        $currentPhase = $cycle->currentPhase;
        if ($currentPhase) {
            $phasesReport[] = $this->buildPhaseEntry($currentPhase, 'running');
            $report->update(['phases_json' => $phasesReport]);
        }

        while (true) {
            try {
                $nowIso = now()->toIso8601String();
                if (! empty($phasesReport)) {
                    $lastIndex = count($phasesReport) - 1;
                    $phasesReport[$lastIndex]['completed_at'] = $nowIso;
                    $phasesReport[$lastIndex]['status'] = 'completed';
                }

                $cycle = $this->growCycleService->advancePhase($cycle, $userId);
                $cycle = $cycle->fresh(['currentPhase']);
                $newPhase = $cycle->currentPhase;
                if ($newPhase) {
                    $phasesReport[] = $this->buildPhaseEntry($newPhase, 'running');
                }

                $report->update(['phases_json' => $phasesReport]);
                $this->recordSimulationEvent(
                    $simulation->id,
                    $simZone->id,
                    'laravel',
                    'phase',
                    'advanced',
                    'Переход к следующей фазе',
                    [
                        'phase_id' => $newPhase?->id,
                        'phase_index' => $newPhase?->phase_index,
                        'phase_name' => $newPhase?->name,
                    ]
                );
            } catch (\DomainException $e) {
                break;
            }
        }

        $errors = [];
        try {
            $cycle = $this->growCycleService->harvest($cycle, ['batch_label' => 'SIM'], $userId);
            $this->recordSimulationEvent(
                $simulation->id,
                $simZone->id,
                'laravel',
                'cycle',
                'harvested',
                'Цикл симуляции завершен',
                ['grow_cycle_id' => $cycle->id]
            );
        } catch (\Throwable $e) {
            $errors[] = [
                'message' => $e->getMessage(),
                'type' => get_class($e),
            ];
            $this->recordSimulationEvent(
                $simulation->id,
                $simZone->id,
                'laravel',
                'cycle',
                'failed',
                'Ошибка завершения цикла симуляции',
                ['error' => $e->getMessage()],
                'error'
            );
        }

        if (! empty($phasesReport)) {
            $lastIndex = count($phasesReport) - 1;
            if (empty($phasesReport[$lastIndex]['completed_at'])) {
                $phasesReport[$lastIndex]['completed_at'] = now()->toIso8601String();
                $phasesReport[$lastIndex]['status'] = 'completed';
            }
        }

        $finishedAt = now();
        $metrics = $this->buildReportMetrics($simulation->id, $simZone->id, $cycle, $phasesReport, $finishedAt);

        $report->update([
            'status' => empty($errors) ? 'completed' : 'failed',
            'finished_at' => $finishedAt,
            'phases_json' => $phasesReport,
            'metrics_json' => $metrics,
            'errors_json' => empty($errors) ? null : $errors,
        ]);

        $this->recordSimulationEvent(
            $simulation->id,
            $simZone->id,
            'laravel',
            'report',
            empty($errors) ? 'completed' : 'failed',
            'Отчет симуляции сформирован',
            ['report_id' => $report->id]
        );

        return $report->fresh();
    }

    private function buildPhaseEntry($phase, string $status): array
    {
        return [
            'phase_id' => $phase->id,
            'phase_index' => $phase->phase_index,
            'name' => $phase->name,
            'started_at' => $phase->started_at?->toIso8601String(),
            'completed_at' => null,
            'status' => $status,
        ];
    }

    private function buildReportMetrics(int $simulationId, int $zoneId, GrowCycle $cycle, array $phases, Carbon $finishedAt): array
    {
        $startedAt = $cycle->started_at ?? $cycle->created_at ?? now();
        $durationSeconds = max(0, $finishedAt->diffInSeconds($startedAt, false));

        return [
            'phases_count' => count($phases),
            'nodes_count' => DeviceNode::query()->where('zone_id', $zoneId)->count(),
            'events_count' => DB::table('simulation_events')->where('simulation_id', $simulationId)->count(),
            'cycle_status' => $cycle->status,
            'duration_seconds' => $durationSeconds,
        ];
    }

    private function resolveSimulationUserId(): int
    {
        $userId = User::query()->orderBy('id')->value('id');
        if (! $userId) {
            throw new \RuntimeException('No users available to run simulation actions.');
        }

        return (int) $userId;
    }

    private function recordSimulationEvent(
        int $simulationId,
        int $zoneId,
        string $service,
        string $stage,
        string $status,
        string $message,
        array $payload = [],
        string $level = 'info',
    ): void {
        try {
            DB::table('simulation_events')->insert([
                'simulation_id' => $simulationId,
                'zone_id' => $zoneId,
                'service' => $service,
                'stage' => $stage,
                'status' => $status,
                'level' => $level,
                'message' => $message,
                'payload' => $payload ? json_encode($payload, JSON_UNESCAPED_UNICODE) : null,
                'occurred_at' => now(),
                'created_at' => now(),
            ]);
        } catch (\Throwable $e) {
            Log::warning('Failed to record simulation event', [
                'simulation_id' => $simulationId,
                'zone_id' => $zoneId,
                'service' => $service,
                'stage' => $stage,
                'status' => $status,
                'error' => $e->getMessage(),
            ]);
        }
    }
}
