<?php

namespace App\Services;

use App\Models\Zone;
use App\Support\Automation\ZoneLogicProfileNormalizer;
use App\Support\Automation\ZoneLogicProfile;
use Carbon\Carbon;
use Illuminate\Support\Collection;
use Illuminate\Support\Facades\DB;

class ZoneLogicProfileService
{
    public function __construct(
        private readonly AutomationConfigDocumentService $documents,
        private readonly ZoneLogicProfileNormalizer $normalizer,
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
    public function upsertProfile(Zone $zone, string $mode, array $subsystems, bool $activate, ?int $userId): ZoneLogicProfile
    {
        $normalizedSubsystems = $this->normalizer->normalizeSubsystems($subsystems);
        $commandPlans = $this->normalizer->buildCommandPlans($normalizedSubsystems);
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
    public function resolveActiveProfileForZone(int $zoneId): ?ZoneLogicProfile
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
    public function resolveProfileByMode(int $zoneId, string $mode): ?ZoneLogicProfile
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
            ->map(fn (array $profile): ZoneLogicProfile => $this->makeTransientProfile($zoneId, $profile))
            ->sortByDesc(fn (ZoneLogicProfile $profile): bool => $profile->isActive)
            ->values();
    }

    protected function mapProfilesForResponse(Collection $profiles): array
    {
        $result = [];

        foreach ($profiles as $profile) {
            if (! $profile instanceof ZoneLogicProfile) {
                continue;
            }

            $result[$profile->mode] = [
                'mode' => $profile->mode,
                'is_active' => $profile->isActive,
                'subsystems' => $profile->subsystems,
                'updated_at' => $profile->updatedAt?->toIso8601String(),
                'created_at' => $profile->createdAt?->toIso8601String(),
                'updated_by' => $profile->updatedBy,
                'created_by' => $profile->createdBy,
            ];
        }

        return $result;
    }

    /**
     * @param  array<string, mixed>  $payload
     */
    private function makeTransientProfile(int $zoneId, array $payload): ZoneLogicProfile
    {
        return new ZoneLogicProfile(
            id: null,
            zoneId: $zoneId,
            mode: (string) ($payload['mode'] ?? ''),
            subsystems: is_array($payload['subsystems'] ?? null) ? $payload['subsystems'] : [],
            commandPlans: is_array($payload['command_plans'] ?? null) ? $payload['command_plans'] : [],
            isActive: (bool) ($payload['is_active'] ?? false),
            createdBy: isset($payload['created_by']) ? (int) $payload['created_by'] : null,
            updatedBy: isset($payload['updated_by']) ? (int) $payload['updated_by'] : null,
            createdAt: $this->coerceDateTime($payload['created_at'] ?? null),
            updatedAt: $this->coerceDateTime($payload['updated_at'] ?? null),
        );
    }

    /**
     * @param  array<string, mixed>  $subsystems
     */
    protected function emitProfileUpdatedZoneEvent(
        int $zoneId,
        ?int $profileId,
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
            'entity_id' => $profileId !== null && $profileId > 0 ? (string) $profileId : null,
            'server_ts' => (int) floor(microtime(true) * 1000),
            'payload_json' => json_encode($payload, JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES),
            'created_at' => now('UTC'),
        ]);
    }

    private function coerceDateTime(mixed $value): ?Carbon
    {
        if ($value instanceof Carbon) {
            return $value;
        }

        if ($value instanceof \DateTimeInterface) {
            return Carbon::instance($value);
        }

        if (! is_string($value) || trim($value) === '') {
            return null;
        }

        return Carbon::parse($value);
    }
}
