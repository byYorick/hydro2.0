<?php

namespace App\Services;

use App\Models\ChannelBinding;
use App\Models\DeviceNode;
use App\Models\InfrastructureInstance;
use App\Models\NodeChannel;
use App\Models\Zone;
use App\Support\PumpCalibrationCatalog;
use Illuminate\Support\Facades\Log;

/**
 * При UI-привязке узла к зоне создаёт channel_bindings для канонических ролей,
 * если на ноде уже есть подходящие ACTUATOR-каналы (pump_main, valve_drain, dosing…).
 *
 * Не перезаписывает уже занятую role в зоне и не трогает чужой node_channel_id.
 */
class ZoneChannelAutoBinder
{
    /**
     * role => channel candidates (priority order).
     *
     * @var array<string, array<int, string>>
     */
    public const ROLE_CHANNEL_CANDIDATES = [
        'pump_main' => ['pump_main'],
        'drain' => ['valve_drain', 'drain', 'drain_main', 'drain_valve'],
        'pump_acid' => ['pump_acid'],
        'pump_base' => ['pump_base'],
        'pump_a' => ['pump_a'],
        'pump_b' => ['pump_b'],
        'pump_c' => ['pump_c'],
        'pump_d' => ['pump_d'],
    ];

    /**
     * @var array<string, array{label: string, asset_type: string, required: bool}>
     */
    private const ROLE_INFRA = [
        'pump_main' => ['label' => 'Auto Main Pump', 'asset_type' => 'PUMP', 'required' => true],
        'drain' => ['label' => 'Auto Drain', 'asset_type' => 'DRAIN', 'required' => true],
        'pump_acid' => ['label' => 'Auto pH Down Pump', 'asset_type' => 'PUMP', 'required' => true],
        'pump_base' => ['label' => 'Auto pH Up Pump', 'asset_type' => 'PUMP', 'required' => true],
        'pump_a' => ['label' => 'Auto EC NPK Pump', 'asset_type' => 'PUMP', 'required' => true],
        'pump_b' => ['label' => 'Auto EC Calcium Pump', 'asset_type' => 'PUMP', 'required' => false],
        'pump_c' => ['label' => 'Auto EC Magnesium Pump', 'asset_type' => 'PUMP', 'required' => false],
        'pump_d' => ['label' => 'Auto EC Micro Pump', 'asset_type' => 'PUMP', 'required' => false],
    ];

    /**
     * @return array<int, string> Roles that were created or already satisfied by this node
     */
    public function bindFromNode(Zone|int $zone, DeviceNode $node): array
    {
        $zoneId = $zone instanceof Zone ? (int) $zone->id : (int) $zone;
        if ($zoneId <= 0 || ! $node->exists) {
            return [];
        }

        $node->loadMissing('channels');
        $bound = [];

        foreach (self::ROLE_CHANNEL_CANDIDATES as $role => $candidates) {
            if ($this->zoneHasRole($zoneId, $role)) {
                if ($this->nodeOwnsRole($zoneId, $role, (int) $node->id)) {
                    $bound[] = $role;
                }

                continue;
            }

            $channel = $this->findMatchingActuatorChannel($node, $candidates);
            if (! $channel) {
                continue;
            }

            if (ChannelBinding::query()->where('node_channel_id', $channel->id)->exists()) {
                continue;
            }

            $infra = $this->ensureInfrastructure($zoneId, $role);
            ChannelBinding::query()->create([
                'infrastructure_instance_id' => $infra->id,
                'node_channel_id' => $channel->id,
                'direction' => 'actuator',
                'role' => $role,
            ]);

            $bound[] = $role;
            Log::info('ZoneChannelAutoBinder: bound role from node channel', [
                'zone_id' => $zoneId,
                'node_id' => $node->id,
                'node_uid' => $node->uid,
                'role' => $role,
                'channel' => $channel->channel,
                'node_channel_id' => $channel->id,
            ]);
        }

        return array_values(array_unique($bound));
    }

    private function zoneHasRole(int $zoneId, string $role): bool
    {
        return ChannelBinding::query()
            ->where('role', $role)
            ->whereHas('infrastructureInstance', function ($query) use ($zoneId) {
                $query->where('owner_type', 'zone')->where('owner_id', $zoneId);
            })
            ->exists();
    }

    private function nodeOwnsRole(int $zoneId, string $role, int $nodeId): bool
    {
        return ChannelBinding::query()
            ->where('role', $role)
            ->whereHas('infrastructureInstance', function ($query) use ($zoneId) {
                $query->where('owner_type', 'zone')->where('owner_id', $zoneId);
            })
            ->whereHas('nodeChannel', function ($query) use ($nodeId) {
                $query->where('node_id', $nodeId);
            })
            ->exists();
    }

    /**
     * @param  array<int, string>  $candidates
     */
    private function findMatchingActuatorChannel(DeviceNode $node, array $candidates): ?NodeChannel
    {
        $normalized = array_map(
            static fn (string $name): string => strtolower(trim($name)),
            $candidates
        );

        /** @var NodeChannel|null $best */
        $best = null;
        $bestPriority = PHP_INT_MAX;

        foreach ($node->channels as $channel) {
            if (! $channel instanceof NodeChannel) {
                continue;
            }
            if (strtolower((string) ($channel->type ?? '')) !== 'actuator') {
                continue;
            }

            $name = strtolower(trim((string) ($channel->channel ?? '')));
            $priority = array_search($name, $normalized, true);
            if ($priority === false) {
                // dosing: channel name OR actuator_type in config
                $actuatorType = strtolower(trim((string) data_get($channel->config, 'actuator_type', '')));
                if ($actuatorType !== '' && PumpCalibrationCatalog::isDosingRole($actuatorType)) {
                    $priority = array_search($actuatorType, $normalized, true);
                }
            }
            if ($priority === false) {
                continue;
            }
            if ($priority < $bestPriority) {
                $bestPriority = (int) $priority;
                $best = $channel;
            }
        }

        return $best;
    }

    private function ensureInfrastructure(int $zoneId, string $role): InfrastructureInstance
    {
        $spec = self::ROLE_INFRA[$role] ?? [
            'label' => 'Auto '.$role,
            'asset_type' => 'PUMP',
            'required' => false,
        ];

        $instance = InfrastructureInstance::query()->firstOrCreate(
            [
                'owner_type' => 'zone',
                'owner_id' => $zoneId,
                'label' => $spec['label'],
            ],
            [
                'asset_type' => $spec['asset_type'],
                'required' => $spec['required'],
            ]
        );

        if (
            $instance->asset_type !== $spec['asset_type']
            || (bool) $instance->required !== (bool) $spec['required']
        ) {
            $instance->asset_type = $spec['asset_type'];
            $instance->required = $spec['required'];
            $instance->save();
        }

        return $instance;
    }
}
