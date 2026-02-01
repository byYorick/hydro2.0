<?php

namespace App\Services;

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
        return DB::transaction(function () use ($sourceZone, $recipeId, $options): array {
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

            if ($fullSimulation) {
                $createdNode = $this->createExtraSimulationNode($simZone);
            }
            $this->ensureSimulationDosingInfrastructure($simZone, $createdNode);

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

        foreach ($sourceZone->nodes as $node) {
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
                'validated' => $node->validated,
                'config' => $node->config,
            ]);

            foreach ($node->channels as $channel) {
                $newChannel = NodeChannel::create([
                    'node_id' => $newNode->id,
                    'channel' => $channel->channel,
                    'type' => $channel->type,
                    'metric' => $channel->metric,
                    'unit' => $channel->unit,
                    'config' => $channel->config,
                ]);
                $channelMap[$channel->id] = $newChannel->id;
            }
        }

        return $channelMap;
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
                'start_immediately' => true,
                'notes' => 'Simulation cycle',
                'batch_label' => 'SIM',
            ],
            null
        );

        $cycleSettings = $cycle->settings ?? [];
        $cycleSettings['simulation'] = [
            'source_zone_id' => $sourceZone->id,
        ];
        $cycle->update(['settings' => $cycleSettings]);

        return $cycle;
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

    private function createExtraSimulationNode(Zone $simZone): DeviceNode
    {
        $node = DeviceNode::create([
            'zone_id' => $simZone->id,
            'uid' => 'sim-node-' . Str::uuid()->toString(),
            'name' => 'SIM Node',
            'type' => 'ph',
            'fw_version' => 'sim',
            'hardware_revision' => 'sim',
            'hardware_id' => 'sim-hw-' . Str::uuid()->toString(),
            'status' => 'online',
            'lifecycle_state' => NodeLifecycleState::ASSIGNED_TO_ZONE,
            'validated' => true,
            'config' => [
                'source' => 'simulation',
            ],
        ]);

        $channels = [
            ['channel' => 'ph_sensor', 'type' => 'SENSOR', 'metric' => 'PH', 'unit' => 'pH'],
            ['channel' => 'ec_sensor', 'type' => 'SENSOR', 'metric' => 'EC', 'unit' => 'mS/cm'],
            ['channel' => 'solution_temp_c', 'type' => 'SENSOR', 'metric' => 'TEMPERATURE', 'unit' => '°C'],
            ['channel' => 'air_temp_c', 'type' => 'SENSOR', 'metric' => 'TEMPERATURE', 'unit' => '°C'],
            ['channel' => 'air_rh', 'type' => 'SENSOR', 'metric' => 'HUMIDITY', 'unit' => '%'],
            ['channel' => 'main_pump', 'type' => 'ACTUATOR', 'metric' => 'PUMP', 'unit' => ''],
            ['channel' => 'drain_pump', 'type' => 'ACTUATOR', 'metric' => 'PUMP', 'unit' => ''],
            ['channel' => 'fan', 'type' => 'ACTUATOR', 'metric' => 'FAN', 'unit' => ''],
            ['channel' => 'heater', 'type' => 'ACTUATOR', 'metric' => 'HEATER', 'unit' => ''],
            ['channel' => 'light', 'type' => 'ACTUATOR', 'metric' => 'LIGHT', 'unit' => ''],
            ['channel' => 'mister', 'type' => 'ACTUATOR', 'metric' => 'MISTER', 'unit' => ''],
            ['channel' => 'fan_pwm', 'type' => 'ACTUATOR', 'metric' => 'PWM', 'unit' => 'int', 'config' => ['actuator_type' => 'PWM']],
        ];

        foreach ($channels as $channel) {
            NodeChannel::create(array_merge($channel, [
                'node_id' => $node->id,
                'config' => $channel['config'] ?? null,
            ]));
        }

        return $node;
    }

    private function ensureSimulationDosingInfrastructure(Zone $simZone, ?DeviceNode $preferredNode = null): void
    {
        $capabilities = $simZone->capabilities ?? [];
        $phControl = (bool) ($capabilities['ph_control'] ?? false);
        $ecControl = (bool) ($capabilities['ec_control'] ?? false);

        if (! $phControl && ! $ecControl) {
            return;
        }

        $zoneNodeIds = DeviceNode::query()
            ->where('zone_id', $simZone->id)
            ->pluck('id')
            ->all();

        if (empty($zoneNodeIds)) {
            return;
        }

        $existingRoles = ChannelBinding::query()
            ->join('infrastructure_instances as ii', 'ii.id', '=', 'channel_bindings.infrastructure_instance_id')
            ->where('ii.owner_type', 'zone')
            ->where('ii.owner_id', $simZone->id)
            ->pluck('channel_bindings.role')
            ->all();
        $existingRoleSet = array_fill_keys($existingRoles, true);

        $targetNode = $preferredNode;
        if (! $targetNode) {
            $targetNode = DeviceNode::query()
                ->where('zone_id', $simZone->id)
                ->orderByRaw("CASE WHEN type = 'ph' THEN 0 WHEN type = 'ec' THEN 1 WHEN type = 'irrig' THEN 2 ELSE 3 END")
                ->orderBy('id')
                ->first();
        }

        if (! $targetNode) {
            return;
        }

        $definitions = [
            'ph_acid_pump' => [
                'channel' => 'pump_acid',
                'label' => 'Насос дозирования кислоты',
                'required' => true,
                'enabled' => $phControl,
            ],
            'ph_base_pump' => [
                'channel' => 'pump_base',
                'label' => 'Насос дозирования щёлочи',
                'required' => true,
                'enabled' => $phControl,
            ],
            'ec_nutrient_pump' => [
                'channel' => 'pump_nutrient',
                'label' => 'Насос питательных веществ',
                'required' => true,
                'enabled' => $ecControl,
            ],
        ];

        foreach ($definitions as $role => $definition) {
            if (! $definition['enabled'] || isset($existingRoleSet[$role])) {
                continue;
            }

            $nodeChannel = NodeChannel::query()
                ->whereIn('node_id', $zoneNodeIds)
                ->where('channel', $definition['channel'])
                ->first();

            if (! $nodeChannel) {
                $nodeChannel = NodeChannel::create([
                    'node_id' => $targetNode->id,
                    'channel' => $definition['channel'],
                    'type' => 'ACTUATOR',
                    'metric' => 'PUMP',
                    'unit' => '',
                ]);
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
