<?php

namespace App\Services;

use App\Models\ChannelBinding;
use App\Models\Greenhouse;
use App\Models\GreenhouseAutomationLogicProfile;
use Illuminate\Support\Collection;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Schema;
use RuntimeException;

class GreenhouseAutomationLogicProfileService
{
    public function isProfilesTableReady(): bool
    {
        return Schema::hasTable('greenhouse_automation_logic_profiles');
    }

    /**
     * Получить профили логики автоматики теплицы, сгруппированные по режимам.
     */
    public function getProfilesPayload(Greenhouse $greenhouse): array
    {
        if (! $this->isProfilesTableReady()) {
            return [
                'active_mode' => null,
                'profiles' => [],
                'bindings' => $this->getClimateBindingsPayload($greenhouse->id),
                'storage_ready' => false,
            ];
        }

        $profiles = $this->getProfilesForGreenhouse($greenhouse->id);
        $activeProfile = $this->resolveActiveProfileForGreenhouse($greenhouse->id);

        return [
            'active_mode' => $activeProfile?->mode,
            'profiles' => $this->mapProfilesForResponse($profiles),
            'bindings' => $this->getClimateBindingsPayload($greenhouse->id),
            'storage_ready' => true,
        ];
    }

    /**
     * Создать/обновить greenhouse profile.
     */
    public function upsertProfile(
        Greenhouse $greenhouse,
        string $mode,
        array $subsystems,
        bool $activate,
        ?int $userId
    ): GreenhouseAutomationLogicProfile {
        if (! $this->isProfilesTableReady()) {
            throw new RuntimeException(
                'Greenhouse climate storage is not initialized. Run php artisan migrate to create greenhouse_automation_logic_profiles.'
            );
        }

        $normalizedSubsystems = $this->normalizeSubsystemsForStorage($subsystems);
        $commandPlans = $this->buildCommandPlans($normalizedSubsystems);

        return DB::transaction(function () use (
            $greenhouse,
            $mode,
            $normalizedSubsystems,
            $commandPlans,
            $activate,
            $userId
        ): GreenhouseAutomationLogicProfile {
            if ($activate) {
                GreenhouseAutomationLogicProfile::query()
                    ->where('greenhouse_id', $greenhouse->id)
                    ->where('mode', '!=', $mode)
                    ->where('is_active', true)
                    ->update(['is_active' => false, 'updated_by' => $userId]);
            }

            $profile = GreenhouseAutomationLogicProfile::query()->firstOrNew([
                'greenhouse_id' => $greenhouse->id,
                'mode' => $mode,
            ]);

            if (! $profile->exists) {
                $profile->created_by = $userId;
            }

            $profile->subsystems = $normalizedSubsystems;
            $profile->command_plans = $commandPlans;
            $profile->is_active = $activate || (bool) $profile->is_active;
            $profile->updated_by = $userId;
            $profile->save();

            return $profile->fresh() ?? $profile;
        });
    }

    public function resolveActiveProfileForGreenhouse(int $greenhouseId): ?GreenhouseAutomationLogicProfile
    {
        if (! $this->isProfilesTableReady()) {
            return null;
        }

        $allowedModes = GreenhouseAutomationLogicProfile::allowedModes();

        $activeAllowedProfile = GreenhouseAutomationLogicProfile::query()
            ->where('greenhouse_id', $greenhouseId)
            ->where('is_active', true)
            ->whereIn('mode', $allowedModes)
            ->orderByDesc('updated_at')
            ->first();
        if ($activeAllowedProfile instanceof GreenhouseAutomationLogicProfile) {
            return $activeAllowedProfile;
        }

        $hasUnsupportedActiveProfile = GreenhouseAutomationLogicProfile::query()
            ->where('greenhouse_id', $greenhouseId)
            ->where('is_active', true)
            ->whereNotIn('mode', $allowedModes)
            ->exists();
        if (! $hasUnsupportedActiveProfile) {
            return null;
        }

        return GreenhouseAutomationLogicProfile::query()
            ->where('greenhouse_id', $greenhouseId)
            ->whereIn('mode', $allowedModes)
            ->orderByRaw("CASE mode WHEN 'working' THEN 0 WHEN 'setup' THEN 1 ELSE 2 END")
            ->orderByDesc('updated_at')
            ->first();
    }

    protected function getProfilesForGreenhouse(int $greenhouseId): Collection
    {
        if (! $this->isProfilesTableReady()) {
            return collect();
        }

        return GreenhouseAutomationLogicProfile::query()
            ->where('greenhouse_id', $greenhouseId)
            ->orderByDesc('is_active')
            ->orderByRaw("CASE mode WHEN 'working' THEN 0 WHEN 'setup' THEN 1 ELSE 2 END")
            ->orderByDesc('updated_at')
            ->get();
    }

    protected function mapProfilesForResponse(Collection $profiles): array
    {
        $result = [];

        foreach ($profiles as $profile) {
            if (! $profile instanceof GreenhouseAutomationLogicProfile) {
                continue;
            }

            $result[$profile->mode] = [
                'mode' => $profile->mode,
                'is_active' => (bool) $profile->is_active,
                'subsystems' => is_array($profile->subsystems) ? $profile->subsystems : [],
                'updated_at' => $profile->updated_at?->toIso8601String(),
                'created_at' => $profile->created_at?->toIso8601String(),
                'updated_by' => $profile->updated_by,
                'created_by' => $profile->created_by,
            ];
        }

        return $result;
    }

    protected function normalizeSubsystemsForStorage(array $subsystems): array
    {
        $climate = $subsystems['climate'] ?? null;
        if (! is_array($climate) || array_is_list($climate)) {
            return [];
        }

        $entry = [
            'enabled' => (bool) ($climate['enabled'] ?? false),
        ];

        if (isset($climate['execution']) && is_array($climate['execution']) && ! array_is_list($climate['execution'])) {
            $entry['execution'] = $climate['execution'];
        }

        return [
            'climate' => $entry,
        ];
    }

    /**
     * @param  array<string, mixed>  $subsystems
     * @return array<string, mixed>
     */
    protected function buildCommandPlans(array $subsystems): array
    {
        $execution = data_get($subsystems, 'climate.execution');
        $execution = is_array($execution) && ! array_is_list($execution) ? $execution : [];

        return [
            'schema_version' => 1,
            'plan_version' => 1,
            'source' => 'greenhouse_automation_logic_profile_upsert',
            'plans' => [
                'climate' => [
                    'execution' => $execution,
                ],
            ],
        ];
    }

    /**
     * @return array{
     *   climate_sensors: array<int, int>,
     *   weather_station_sensors: array<int, int>,
     *   vent_actuators: array<int, int>,
     *   fan_actuators: array<int, int>
     * }
     */
    protected function getClimateBindingsPayload(int $greenhouseId): array
    {
        $bindings = ChannelBinding::query()
            ->select(['channel_bindings.role', 'node_channels.node_id'])
            ->join('infrastructure_instances', 'infrastructure_instances.id', '=', 'channel_bindings.infrastructure_instance_id')
            ->join('node_channels', 'node_channels.id', '=', 'channel_bindings.node_channel_id')
            ->where('infrastructure_instances.owner_type', 'greenhouse')
            ->where('infrastructure_instances.owner_id', $greenhouseId)
            ->whereIn('channel_bindings.role', [
                'climate_sensor',
                'weather_station_sensor',
                'vent_actuator',
                'fan_actuator',
            ])
            ->get();

        return [
            'climate_sensors' => $this->mapBindingRoleNodeIds($bindings, 'climate_sensor'),
            'weather_station_sensors' => $this->mapBindingRoleNodeIds($bindings, 'weather_station_sensor'),
            'vent_actuators' => $this->mapBindingRoleNodeIds($bindings, 'vent_actuator'),
            'fan_actuators' => $this->mapBindingRoleNodeIds($bindings, 'fan_actuator'),
        ];
    }

    /**
     * @param  Collection<int, object>  $bindings
     * @return array<int, int>
     */
    protected function mapBindingRoleNodeIds(Collection $bindings, string $role): array
    {
        return $bindings
            ->filter(static fn ($binding): bool => (string) ($binding->role ?? '') === $role)
            ->map(static fn ($binding): ?int => isset($binding->node_id) ? (int) $binding->node_id : null)
            ->filter(static fn (?int $nodeId): bool => is_int($nodeId) && $nodeId > 0)
            ->unique()
            ->values()
            ->all();
    }
}
