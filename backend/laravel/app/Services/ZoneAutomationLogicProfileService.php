<?php

namespace App\Services;

use App\Models\Zone;
use App\Models\ZoneAutomationLogicProfile;
use Illuminate\Support\Collection;

class ZoneAutomationLogicProfileService
{
    public function __construct(
        private readonly AutomationConfigDocumentService $documents,
    ) {
    }

    /**
     * Получить профили логики автоматики зоны, сгруппированные по режимам.
     */
    public function getProfilesPayload(Zone $zone): array
    {
        $payload = $this->documents->getPayload(
            AutomationConfigRegistry::NAMESPACE_ZONE_LOGIC_PROFILE,
            AutomationConfigRegistry::SCOPE_ZONE,
            (int) $zone->id,
            true
        );
        $profiles = $this->getProfilesForZone($zone->id);
        $activeProfile = $this->resolveActiveProfileForZone($zone->id);

        return [
            'active_mode' => is_string($payload['active_mode'] ?? null) ? $payload['active_mode'] : $activeProfile?->mode,
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
        $payload = $this->documents->getPayload(
            AutomationConfigRegistry::NAMESPACE_ZONE_LOGIC_PROFILE,
            AutomationConfigRegistry::SCOPE_ZONE,
            (int) $zone->id,
            true
        );
        $profiles = is_array($payload['profiles'] ?? null) && ! array_is_list($payload['profiles'])
            ? $payload['profiles']
            : [];
        $profiles[$mode] = [
            'mode' => $mode,
            'is_active' => $activate || (($profiles[$mode]['is_active'] ?? false) === true),
            'subsystems' => $normalizedSubsystems,
            'command_plans' => $commandPlans,
            'updated_at' => now()->toIso8601String(),
            'updated_by' => $userId,
            'created_by' => $profiles[$mode]['created_by'] ?? $userId,
            'created_at' => $profiles[$mode]['created_at'] ?? now()->toIso8601String(),
        ];

        if ($activate) {
            foreach ($profiles as $profileMode => &$profilePayload) {
                if ($profileMode === $mode || ! is_array($profilePayload)) {
                    continue;
                }
                $profilePayload['is_active'] = false;
            }
            unset($profilePayload);
            $payload['active_mode'] = $mode;
        } elseif (! isset($payload['active_mode']) || $payload['active_mode'] === null) {
            $payload['active_mode'] = $mode;
        }

        $payload['profiles'] = $profiles;
        $this->documents->upsertDocument(
            AutomationConfigRegistry::NAMESPACE_ZONE_LOGIC_PROFILE,
            AutomationConfigRegistry::SCOPE_ZONE,
            (int) $zone->id,
            $payload,
            $userId,
            'zone_logic_profile'
        );

        $this->emitProfileUpdatedZoneEvent(
            zoneId: (int) $zone->id,
            profileId: 0,
            mode: $mode,
            subsystems: $normalizedSubsystems,
            userId: $userId,
        );

        return $this->makeTransientProfile((int) $zone->id, $profiles[$mode]);
    }

    /**
     * Разрешить активный runtime-профиль для зоны.
     */
    public function resolveActiveProfileForZone(int $zoneId): ?ZoneAutomationLogicProfile
    {
        $payload = $this->documents->getPayload(
            AutomationConfigRegistry::NAMESPACE_ZONE_LOGIC_PROFILE,
            AutomationConfigRegistry::SCOPE_ZONE,
            $zoneId,
            false
        );
        $activeMode = is_string($payload['active_mode'] ?? null) ? $payload['active_mode'] : null;
        $profiles = is_array($payload['profiles'] ?? null) && ! array_is_list($payload['profiles']) ? $payload['profiles'] : [];
        $activeProfile = is_string($activeMode) && is_array($profiles[$activeMode] ?? null) ? $profiles[$activeMode] : null;

        return is_array($activeProfile) ? $this->makeTransientProfile($zoneId, $activeProfile) : null;
    }

    /**
     * Получить профиль конкретного режима для зоны.
     */
    public function resolveProfileByMode(int $zoneId, string $mode): ?ZoneAutomationLogicProfile
    {
        $payload = $this->documents->getPayload(
            AutomationConfigRegistry::NAMESPACE_ZONE_LOGIC_PROFILE,
            AutomationConfigRegistry::SCOPE_ZONE,
            $zoneId,
            false
        );
        $profile = data_get($payload, "profiles.{$mode}");

        return is_array($profile) ? $this->makeTransientProfile($zoneId, $profile) : null;
    }

    protected function getProfilesForZone(int $zoneId): Collection
    {
        $payload = $this->documents->getPayload(
            AutomationConfigRegistry::NAMESPACE_ZONE_LOGIC_PROFILE,
            AutomationConfigRegistry::SCOPE_ZONE,
            $zoneId,
            false
        );
        $profiles = is_array($payload['profiles'] ?? null) && ! array_is_list($payload['profiles']) ? $payload['profiles'] : [];

        return collect($profiles)
            ->filter(fn (mixed $profile): bool => is_array($profile))
            ->map(fn (array $profile): ZoneAutomationLogicProfile => $this->makeTransientProfile($zoneId, $profile))
            ->sortByDesc(fn (ZoneAutomationLogicProfile $profile): bool => (bool) $profile->is_active)
            ->values();
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

    /**
     * @param  array<string, mixed>  $payload
     */
    private function makeTransientProfile(int $zoneId, array $payload): ZoneAutomationLogicProfile
    {
        $profile = new ZoneAutomationLogicProfile();
        $profile->forceFill([
            'zone_id' => $zoneId,
            'mode' => (string) ($payload['mode'] ?? ''),
            'subsystems' => is_array($payload['subsystems'] ?? null) ? $payload['subsystems'] : [],
            'command_plans' => is_array($payload['command_plans'] ?? null) ? $payload['command_plans'] : [],
            'is_active' => (bool) ($payload['is_active'] ?? false),
            'created_by' => $payload['created_by'] ?? null,
            'updated_by' => $payload['updated_by'] ?? null,
            'created_at' => $payload['created_at'] ?? null,
            'updated_at' => $payload['updated_at'] ?? null,
        ]);

        return $profile;
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
