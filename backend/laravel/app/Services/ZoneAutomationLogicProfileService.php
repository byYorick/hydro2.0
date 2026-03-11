<?php

namespace App\Services;

use App\Models\Zone;
use App\Models\ZoneAutomationLogicProfile;
use Illuminate\Support\Collection;
use Illuminate\Support\Facades\DB;

class ZoneAutomationLogicProfileService
{
    /**
     * Получить профили логики автоматики зоны, сгруппированные по режимам.
     */
    public function getProfilesPayload(Zone $zone): array
    {
        $profiles = $this->getProfilesForZone($zone->id);
        $activeProfile = $this->resolveActiveProfileForZone($zone->id);

        return [
            'active_mode' => $activeProfile?->mode,
            'profiles' => $this->mapProfilesForResponse($profiles),
        ];
    }

    /**
     * Создать/обновить профиль логики автоматики для зоны.
     */
    public function upsertProfile(Zone $zone, string $mode, array $subsystems, bool $activate, ?int $userId): ZoneAutomationLogicProfile
    {
        $normalizedSubsystems = $this->normalizeSubsystemsForStorage($subsystems);
        $commandPlans = $this->buildCommandPlans($normalizedSubsystems);

        return DB::transaction(function () use ($zone, $mode, $normalizedSubsystems, $commandPlans, $activate, $userId): ZoneAutomationLogicProfile {
            if ($activate) {
                ZoneAutomationLogicProfile::query()
                    ->where('zone_id', $zone->id)
                    ->where('mode', '!=', $mode)
                    ->where('is_active', true)
                    ->update(['is_active' => false, 'updated_by' => $userId]);
            }

            $profile = ZoneAutomationLogicProfile::query()->firstOrNew([
                'zone_id' => $zone->id,
                'mode' => $mode,
            ]);

            if (!$profile->exists) {
                $profile->created_by = $userId;
            }

            $profile->subsystems = $normalizedSubsystems;
            $profile->command_plans = $commandPlans;
            $profile->is_active = $activate || (bool) $profile->is_active;
            $profile->updated_by = $userId;
            $profile->save();

            $this->emitProfileUpdatedZoneEvent(
                zoneId: (int) $zone->id,
                profileId: (int) ($profile->id ?? 0),
                mode: $mode,
                subsystems: $normalizedSubsystems,
                userId: $userId,
            );

            return $profile->fresh() ?? $profile;
        });
    }

    /**
     * Разрешить активный runtime-профиль для зоны.
     */
    public function resolveActiveProfileForZone(int $zoneId): ?ZoneAutomationLogicProfile
    {
        $allowedModes = ZoneAutomationLogicProfile::allowedModes();

        $activeAllowedProfile = ZoneAutomationLogicProfile::query()
            ->where('zone_id', $zoneId)
            ->where('is_active', true)
            ->whereIn('mode', $allowedModes)
            ->orderByDesc('updated_at')
            ->first();
        if ($activeAllowedProfile instanceof ZoneAutomationLogicProfile) {
            return $activeAllowedProfile;
        }

        $hasUnsupportedActiveProfile = ZoneAutomationLogicProfile::query()
            ->where('zone_id', $zoneId)
            ->where('is_active', true)
            ->whereNotIn('mode', $allowedModes)
            ->exists();
        if (! $hasUnsupportedActiveProfile) {
            return null;
        }

        return ZoneAutomationLogicProfile::query()
            ->where('zone_id', $zoneId)
            ->whereIn('mode', $allowedModes)
            ->orderByRaw("CASE mode WHEN 'working' THEN 0 WHEN 'setup' THEN 1 ELSE 2 END")
            ->orderByDesc('updated_at')
            ->first();
    }

    /**
     * Получить профиль конкретного режима для зоны.
     */
    public function resolveProfileByMode(int $zoneId, string $mode): ?ZoneAutomationLogicProfile
    {
        return ZoneAutomationLogicProfile::query()
            ->where('zone_id', $zoneId)
            ->where('mode', $mode)
            ->first();
    }

    protected function getProfilesForZone(int $zoneId): Collection
    {
        return ZoneAutomationLogicProfile::query()
            ->where('zone_id', $zoneId)
            ->orderByDesc('is_active')
            ->orderByRaw("CASE mode WHEN 'working' THEN 0 WHEN 'setup' THEN 1 ELSE 2 END")
            ->orderByDesc('updated_at')
            ->get();
    }

    protected function mapProfilesForResponse(Collection $profiles): array
    {
        $result = [];

        foreach ($profiles as $profile) {
            if (!$profile instanceof ZoneAutomationLogicProfile) {
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
        $normalized = [];

        foreach ($subsystems as $name => $subsystem) {
            if (!is_string($name) || !is_array($subsystem) || array_is_list($subsystem)) {
                continue;
            }

            $entry = [];
            if (array_key_exists('enabled', $subsystem)) {
                $entry['enabled'] = (bool) $subsystem['enabled'];
            }

            $execution = [];
            if (isset($subsystem['execution']) && is_array($subsystem['execution'])) {
                $execution = $subsystem['execution'];
                if ($name === 'diagnostics') {
                    $execution = $this->normalizeDiagnosticsExecution($execution);
                }
            }

            if (!empty($execution)) {
                $entry['execution'] = $execution;
            }

            if (!empty($entry)) {
                $normalized[$name] = $entry;
            }
        }

        return $normalized;
    }

    /**
     * @param  array<string, mixed>  $execution
     * @return array<string, mixed>
     */
    protected function normalizeDiagnosticsExecution(array $execution): array
    {
        $workflow = $execution['workflow'] ?? null;
        if (is_string($workflow) && strtolower(trim($workflow)) === 'startup') {
            $execution['workflow'] = 'cycle_start';
        }

        return $execution;
    }

    /**
     * @param  array<string, mixed>  $subsystems
     * @return array<string, mixed>
     */
    protected function buildCommandPlans(array $subsystems): array
    {
        $execution = data_get($subsystems, 'diagnostics.execution');
        $execution = is_array($execution) && ! array_is_list($execution) ? $execution : [];

        $twoTankCommands = data_get($execution, 'two_tank_commands');
        $twoTankCommands = is_array($twoTankCommands) && ! array_is_list($twoTankCommands) ? $twoTankCommands : [];

        $steps = $this->resolveCommandPlanSteps($execution, $twoTankCommands);

        return [
            'schema_version' => 1,
            'plan_version' => 1,
            'source' => 'automation_logic_profile_upsert',
            'plans' => [
                'diagnostics' => [
                    'execution' => $execution,
                    'two_tank_commands' => $twoTankCommands,
                    'steps' => $steps,
                ],
            ],
        ];
    }

    /**
     * @param  array<string, mixed>  $execution
     * @param  array<string, mixed>  $twoTankCommands
     * @return array<int, array<string, mixed>>
     */
    protected function resolveCommandPlanSteps(array $execution, array $twoTankCommands): array
    {
        $fromTwoTankSteps = data_get($twoTankCommands, 'steps');
        if (is_array($fromTwoTankSteps) && ! empty($fromTwoTankSteps)) {
            $normalized = $this->normalizeCommandPlanSteps($fromTwoTankSteps);
            if (! empty($normalized)) {
                return $normalized;
            }
        }

        $rawExecutionSteps = data_get($execution, 'steps');
        if (is_array($rawExecutionSteps) && ! empty($rawExecutionSteps)) {
            $normalized = $this->normalizeCommandPlanSteps($rawExecutionSteps);
            if (! empty($normalized)) {
                return $normalized;
            }
        }

        return $this->buildFallbackStepsFromTwoTankCommands($twoTankCommands);
    }

    /**
     * @param  array<int, mixed>  $rawSteps
     * @return array<int, array<string, mixed>>
     */
    protected function normalizeCommandPlanSteps(array $rawSteps): array
    {
        $steps = [];

        foreach ($rawSteps as $index => $rawStep) {
            if (! is_array($rawStep) || array_is_list($rawStep)) {
                continue;
            }

            $channel = trim((string) ($rawStep['channel'] ?? ''));
            $cmd = trim((string) ($rawStep['cmd'] ?? ''));
            $params = $rawStep['params'] ?? [];
            if ($channel === '' || $cmd === '' || ! is_array($params)) {
                continue;
            }

            $steps[] = [
                'name' => isset($rawStep['name']) ? (string) $rawStep['name'] : 'step_'.((int) $index + 1),
                'channel' => $channel,
                'cmd' => $cmd,
                'params' => $params,
                'timeout_sec' => isset($rawStep['timeout_sec']) ? (int) $rawStep['timeout_sec'] : null,
                'allow_no_effect' => (bool) ($rawStep['allow_no_effect'] ?? false),
                'dedupe_bypass' => (bool) ($rawStep['dedupe_bypass'] ?? false),
            ];
        }

        return $steps;
    }

    /**
     * @param  array<string, mixed>  $twoTankCommands
     * @return array<int, array<string, mixed>>
     */
    protected function buildFallbackStepsFromTwoTankCommands(array $twoTankCommands): array
    {
        $steps = [];

        foreach ($twoTankCommands as $planName => $planCommands) {
            if (! is_string($planName) || ! is_array($planCommands) || ! array_is_list($planCommands)) {
                continue;
            }

            foreach ($planCommands as $position => $rawStep) {
                if (! is_array($rawStep) || array_is_list($rawStep)) {
                    continue;
                }

                $channel = trim((string) ($rawStep['channel'] ?? ''));
                $cmd = trim((string) ($rawStep['cmd'] ?? ''));
                $params = $rawStep['params'] ?? [];
                if ($channel === '' || $cmd === '' || ! is_array($params)) {
                    continue;
                }

                $steps[] = [
                    'name' => $planName.'_'.((int) $position + 1),
                    'channel' => $channel,
                    'cmd' => $cmd,
                    'params' => $params,
                    'allow_no_effect' => (bool) ($rawStep['allow_no_effect'] ?? false),
                    'dedupe_bypass' => (bool) ($rawStep['dedupe_bypass'] ?? false),
                ];
            }
        }

        return $steps;
    }

    /**
     * @param  array<string, mixed>  $subsystems
     */
    protected function emitProfileUpdatedZoneEvent(
        int $zoneId,
        int $profileId,
        string $mode,
        array $subsystems,
        ?int $userId,
    ): void {
        $payload = [
            'profile_id' => $profileId > 0 ? $profileId : null,
            'mode' => $mode,
            'subsystems' => $subsystems,
            'user_id' => $userId,
        ];

        DB::table('zone_events')->insert([
            'zone_id' => $zoneId,
            'type' => 'AUTOMATION_LOGIC_PROFILE_UPDATED',
            'entity_type' => 'automation_logic_profile',
            'entity_id' => $profileId > 0 ? (string) $profileId : null,
            'server_ts' => (int) floor(microtime(true) * 1000),
            'payload_json' => json_encode($payload, JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES),
            'created_at' => now('UTC'),
        ]);
    }
}
