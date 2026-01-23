<?php

namespace App\Services;

use App\Enums\NodeLifecycleState;
use App\Models\ChannelBinding;
use App\Models\DeviceNode;
use App\Models\InfrastructureInstance;
use App\Models\NodeChannel;
use App\Models\Plant;
use App\Models\RecipeRevision;
use App\Models\Zone;
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
     * @return array{zone: Zone, grow_cycle: \App\Models\GrowCycle}
     */
    public function createSimulationContext(Zone $sourceZone, int $recipeId): array
    {
        return DB::transaction(function () use ($sourceZone, $recipeId): array {
            $simZone = Zone::create([
                'uid' => 'sim-' . Str::uuid()->toString(),
                'greenhouse_id' => $sourceZone->greenhouse_id,
                'preset_id' => $sourceZone->preset_id,
                'name' => 'SIM ' . ($sourceZone->name ?: ('Zone ' . $sourceZone->id)),
                'description' => $sourceZone->description,
                'status' => 'offline',
                'health_score' => $sourceZone->health_score,
                'health_status' => $sourceZone->health_status,
                'hardware_profile' => $sourceZone->hardware_profile,
                'capabilities' => $sourceZone->capabilities,
                'water_state' => $sourceZone->water_state,
                'solution_started_at' => $sourceZone->solution_started_at,
                'settings' => $this->buildSimulationSettings($sourceZone),
            ]);

            $channelMap = $this->cloneNodesAndChannels($sourceZone, $simZone);
            $this->cloneInfrastructure($sourceZone, $simZone, $channelMap);

            $cycle = $this->createSimulationGrowCycle($sourceZone, $simZone, $recipeId);

            Log::info('Simulation context created', [
                'source_zone_id' => $sourceZone->id,
                'simulation_zone_id' => $simZone->id,
                'grow_cycle_id' => $cycle->id,
            ]);

            return [
                'zone' => $simZone->fresh(),
                'grow_cycle' => $cycle->fresh(),
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
                'status' => 'offline',
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
                ChannelBinding::create([
                    'infrastructure_instance_id' => $newInstance->id,
                    'node_channel_id' => $newChannelId,
                    'direction' => $binding->direction,
                    'role' => $binding->role,
                ]);
            }
        }
    }

    private function createSimulationGrowCycle(Zone $sourceZone, Zone $simZone, int $recipeId)
    {
        $revision = RecipeRevision::query()
            ->where('recipe_id', $recipeId)
            ->where('status', 'PUBLISHED')
            ->orderByDesc('revision_number')
            ->first();

        if (! $revision) {
            throw new \RuntimeException('Published recipe revision not found for simulation.');
        }

        $plantId = $sourceZone->activeGrowCycle?->plant_id;
        if (! $plantId) {
            $plantId = Plant::query()->orderBy('id')->value('id');
        }
        if (! $plantId) {
            throw new \RuntimeException('No plants available to create simulation grow cycle.');
        }

        $cycle = $this->growCycleService->createCycle(
            $simZone,
            $revision,
            (int) $plantId,
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
}
