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

        return [
            'active_mode' => $this->resolveActiveModeFromCollection($profiles),
            'profiles' => $this->mapProfilesForResponse($profiles),
        ];
    }

    /**
     * Создать/обновить профиль логики автоматики для зоны.
     */
    public function upsertProfile(Zone $zone, string $mode, array $subsystems, bool $activate, ?int $userId): ZoneAutomationLogicProfile
    {
        $normalizedSubsystems = $this->normalizeSubsystemsForStorage($subsystems);

        return DB::transaction(function () use ($zone, $mode, $normalizedSubsystems, $activate, $userId): ZoneAutomationLogicProfile {
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
            $profile->is_active = $activate || (bool) $profile->is_active;
            $profile->updated_by = $userId;
            $profile->save();

            return $profile->fresh() ?? $profile;
        });
    }

    /**
     * Разрешить активный runtime-профиль для зоны.
     */
    public function resolveActiveProfileForZone(int $zoneId): ?ZoneAutomationLogicProfile
    {
        return ZoneAutomationLogicProfile::query()
            ->where('zone_id', $zoneId)
            ->where('is_active', true)
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

    protected function resolveActiveModeFromCollection(Collection $profiles): ?string
    {
        $active = $profiles->firstWhere('is_active', true);
        if ($active instanceof ZoneAutomationLogicProfile) {
            return $active->mode;
        }

        return null;
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
            }

            $legacyTargets = is_array($subsystem['targets'] ?? null) ? $subsystem['targets'] : [];
            if (!empty($legacyTargets)) {
                $execution = array_replace_recursive($this->extractLegacyExecutionPatch($name, $legacyTargets), $execution);
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

    protected function extractLegacyExecutionPatch(string $subsystemName, array $legacyTargets): array
    {
        $nestedExecution = is_array($legacyTargets['execution'] ?? null) ? $legacyTargets['execution'] : [];

        if (in_array($subsystemName, ['ph', 'ec'], true)) {
            return $nestedExecution;
        }

        $flatPatch = $legacyTargets;
        unset($flatPatch['execution']);

        return array_replace_recursive($flatPatch, $nestedExecution);
    }
}
