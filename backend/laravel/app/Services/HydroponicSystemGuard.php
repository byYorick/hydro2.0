<?php

declare(strict_types=1);

namespace App\Services;

use App\Enums\GrowCycleStatus;
use App\Exceptions\UnsupportedHydroponicSystemException;
use App\Models\GrowCycle;
use App\Models\Zone;
use App\Support\Hydroponics\HydroponicSystemCatalog;
use Illuminate\Database\Eloquent\Model;
use Illuminate\Support\Arr;

/**
 * Не даёт запустить капельное исполнение для зоны, у которой явно задан другой тип системы.
 */
class HydroponicSystemGuard
{
    /**
     * @param  list<string|null>  $rawTypes
     */
    public function assertExecutable(array $rawTypes, ?string $environment = null): void
    {
        foreach ($rawTypes as $raw) {
            if (! is_string($raw)) {
                continue;
            }
            if (HydroponicSystemCatalog::refusalCode($raw, $environment) === null) {
                continue;
            }

            throw UnsupportedHydroponicSystemException::forRaw($raw, $environment);
        }
    }

    public function assertZoneIrrigationExecutable(Zone|int $zone, ?GrowCycle $cycle = null): void
    {
        $zoneId = $zone instanceof Zone ? (int) $zone->id : $zone;
        $cycle ??= $this->activeCycle($zoneId);
        $types = [];
        if ($cycle !== null) {
            $types[] = $this->cycleSystemType($cycle);
            $currentPhase = $cycle->relationLoaded('currentPhase')
                ? $cycle->currentPhase
                : $cycle->currentPhase()->first();
            if ($currentPhase instanceof Model) {
                $types = array_merge($types, $this->typesFromPhase($currentPhase));
            }
        }
        $types = array_merge($types, $this->typesFromActiveProfile($zoneId));
        $this->assertExecutable($types, $this->environmentCode($zoneId));
    }

    /**
     * Смена zone.logic_profile при активном цикле не должна подменить исполнение на неподдерживаемый тип.
     *
     * @param  array<string, mixed>  $payload
     */
    public function assertLogicProfileChangeAllowed(int $zoneId, array $payload): void
    {
        if ($this->activeCycle($zoneId) === null) {
            return;
        }

        $this->assertExecutable(
            $this->typesFromLogicProfilePayload($payload),
            $this->environmentCode($zoneId),
        );
    }

    /**
     * @return list<string|null>
     */
    public function typesFromPhase(Model $phase): array
    {
        $types = [];
        $column = $phase->getAttribute('irrigation_system_type');
        if (is_string($column) && trim($column) !== '') {
            $types[] = $column;
        }

        $extensions = $phase->getAttribute('extensions');
        if (! is_array($extensions)) {
            return $types;
        }

        foreach ([
            'subsystems.irrigation.targets.system_type',
            'subsystems.irrigation.execution.system_type',
        ] as $path) {
            $value = Arr::get($extensions, $path);
            if (is_string($value) && trim($value) !== '') {
                $types[] = $value;
            }
        }

        return $types;
    }

    /**
     * @return list<string|null>
     */
    public function typesFromActiveProfile(int $zoneId): array
    {
        $profile = app(ZoneLogicProfileService::class)->resolveActiveProfileForZone($zoneId);
        if ($profile === null) {
            return [];
        }

        return $this->typesFromSubsystems(is_array($profile->subsystems) ? $profile->subsystems : []);
    }

    /**
     * @param  array<string, mixed>  $payload
     * @return list<string|null>
     */
    public function typesFromLogicProfilePayload(array $payload): array
    {
        $profiles = $payload['profiles'] ?? null;
        if (! is_array($profiles)) {
            $subsystems = $payload['subsystems'] ?? null;

            return is_array($subsystems) ? $this->typesFromSubsystems($subsystems) : [];
        }

        $selected = [];
        $activeMode = $payload['active_mode'] ?? null;
        if (is_string($activeMode) && is_array($profiles[$activeMode] ?? null)) {
            $selected[] = $profiles[$activeMode];
        } else {
            foreach ($profiles as $profile) {
                if (is_array($profile) && ($profile['is_active'] ?? false) === true) {
                    $selected[] = $profile;
                }
            }
        }

        if ($selected === []) {
            foreach ($profiles as $profile) {
                if (is_array($profile)) {
                    $selected[] = $profile;
                }
            }
        }

        $types = [];
        foreach ($selected as $profile) {
            $subsystems = $profile['subsystems'] ?? null;
            if (is_array($subsystems)) {
                $types = array_merge($types, $this->typesFromSubsystems($subsystems));
            }
        }

        return $types;
    }

    public function cycleSystemType(GrowCycle $cycle): ?string
    {
        $settings = $cycle->settings;
        if (! is_array($settings)) {
            return null;
        }

        $value = Arr::get($settings, 'irrigation.system_type');

        return is_string($value) && trim($value) !== '' ? $value : null;
    }

    private function environmentCode(int $zoneId): ?string
    {
        if ($zoneId <= 0) {
            return null;
        }

        $zone = Zone::query()->with('greenhouse')->find($zoneId);
        $type = $zone?->greenhouse?->type;

        return is_string($type) && trim($type) !== '' ? strtolower(trim($type)) : null;
    }

    private function activeCycle(int $zoneId): ?GrowCycle
    {
        if ($zoneId <= 0) {
            return null;
        }

        return GrowCycle::query()
            ->where('zone_id', $zoneId)
            ->whereIn('status', [
                GrowCycleStatus::PLANNED,
                GrowCycleStatus::RUNNING,
                GrowCycleStatus::PAUSED,
            ])
            ->latest('id')
            ->first();
    }

    /**
     * @param  array<string, mixed>  $subsystems
     * @return list<string|null>
     */
    private function typesFromSubsystems(array $subsystems): array
    {
        $types = [];
        foreach ([
            'irrigation.targets.system_type',
            'irrigation.execution.system_type',
        ] as $path) {
            $value = Arr::get($subsystems, $path);
            if (is_string($value) && trim($value) !== '') {
                $types[] = $value;
            }
        }

        return $types;
    }
}
