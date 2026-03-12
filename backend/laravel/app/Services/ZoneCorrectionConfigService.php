<?php

namespace App\Services;

use App\Models\User;
use App\Models\Zone;
use App\Models\ZoneCorrectionConfig;
use App\Models\ZoneCorrectionConfigVersion;
use App\Models\ZoneCorrectionPreset;
use App\Models\ZoneEvent;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Schema;

class ZoneCorrectionConfigService
{
    public function getOrCreateForZone(Zone|int $zone): ZoneCorrectionConfig
    {
        $zoneId = $zone instanceof Zone ? $zone->id : (int) $zone;

        $config = ZoneCorrectionConfig::query()
            ->with(['preset', 'updatedBy'])
            ->where('zone_id', $zoneId)
            ->first();

        if ($config) {
            return $config;
        }

        return DB::transaction(function () use ($zoneId) {
            $existing = ZoneCorrectionConfig::query()->where('zone_id', $zoneId)->first();
            if ($existing) {
                return $existing->loadMissing(['preset', 'updatedBy']);
            }

            $resolved = ZoneCorrectionConfigCatalog::defaultResolvedConfig();
            $created = ZoneCorrectionConfig::query()->create([
                'zone_id' => $zoneId,
                'preset_id' => null,
                'base_config' => [],
                'phase_overrides' => [],
                'resolved_config' => $resolved,
                'version' => 1,
                'updated_by' => null,
            ]);

            $this->recordVersion($created, changedBy: null, changeType: 'bootstrap');

            return $created->loadMissing(['preset', 'updatedBy']);
        });
    }

    public function getResponsePayload(Zone|int $zone): array
    {
        $config = $this->getOrCreateForZone($zone);

        return [
            'id' => $config->id,
            'zone_id' => $config->zone_id,
            'preset' => $config->preset ? $this->serializePreset($config->preset) : null,
            'base_config' => $config->base_config ?? [],
            'phase_overrides' => $config->phase_overrides ?? [],
            'resolved_config' => $config->resolved_config ?? ZoneCorrectionConfigCatalog::defaultResolvedConfig(),
            'version' => $config->version,
            'updated_at' => optional($config->updated_at)->toISOString(),
            'updated_by' => $config->updated_by,
            'last_applied_at' => optional($config->last_applied_at)->toISOString(),
            'last_applied_version' => $config->last_applied_version,
            'meta' => [
                'phases' => ZoneCorrectionConfigCatalog::PHASES,
                'defaults' => ZoneCorrectionConfigCatalog::defaults(),
                'field_catalog' => ZoneCorrectionConfigCatalog::fieldCatalog(),
            ],
        ];
    }

    public function listVersions(Zone|int $zone): array
    {
        $zoneId = $zone instanceof Zone ? $zone->id : (int) $zone;

        return ZoneCorrectionConfigVersion::query()
            ->with(['preset', 'changedBy'])
            ->where('zone_id', $zoneId)
            ->orderByDesc('version')
            ->orderByDesc('id')
            ->get()
            ->map(fn (ZoneCorrectionConfigVersion $version) => [
                'id' => $version->id,
                'version' => $version->version,
                'change_type' => $version->change_type,
                'preset' => $version->preset ? $this->serializePreset($version->preset) : null,
                'changed_by' => $version->changed_by,
                'changed_at' => optional($version->changed_at)->toISOString(),
                'base_config' => $version->base_config ?? [],
                'phase_overrides' => $version->phase_overrides ?? [],
                'resolved_config' => $version->resolved_config ?? [],
            ])
            ->all();
    }

    public function upsert(
        Zone|int $zone,
        array $payload,
        ?int $userId = null,
    ): ZoneCorrectionConfig {
        $zoneId = $zone instanceof Zone ? $zone->id : (int) $zone;
        $userId = $this->normalizeExistingUserId($userId);
        $presetId = $payload['preset_id'] ?? null;
        $baseConfig = is_array($payload['base_config'] ?? null) ? $payload['base_config'] : [];
        $phaseOverrides = is_array($payload['phase_overrides'] ?? null) ? $payload['phase_overrides'] : [];

        $preset = null;
        if ($presetId !== null) {
            $preset = ZoneCorrectionPreset::query()
                ->where('id', (int) $presetId)
                ->where('is_active', true)
                ->firstOrFail();
        }

        return DB::transaction(function () use ($zoneId, $preset, $baseConfig, $phaseOverrides, $userId) {
            [$presetBaseConfig, $presetPhaseConfigs] = $this->splitPresetConfig($preset?->config);
            $presetBase = ZoneCorrectionConfigCatalog::merge(
                ZoneCorrectionConfigCatalog::defaults(),
                $presetBaseConfig
            );
            $storedBaseConfig = $this->normalizeStoredOverride($presetBase, $baseConfig);
            $resolvedBase = ZoneCorrectionConfigCatalog::merge($presetBase, $storedBaseConfig);
            $storedPhaseOverrides = $this->normalizeStoredPhaseOverrides(
                resolvedBase: $resolvedBase,
                presetPhaseConfigs: $presetPhaseConfigs,
                phaseOverrides: $phaseOverrides,
            );

            $config = $this->getOrCreateForZone($zoneId);

            $resolved = $this->buildResolvedConfig(
                preset: $preset,
                baseConfig: $storedBaseConfig,
                phaseOverrides: $storedPhaseOverrides,
            );

            $config->fill([
                'preset_id' => $preset?->id,
                'base_config' => $storedBaseConfig,
                'phase_overrides' => $storedPhaseOverrides,
                'resolved_config' => $resolved,
                'version' => (int) $config->version + 1,
                'updated_by' => $userId,
            ]);
            $config->save();

            $this->recordVersion($config, changedBy: $userId, changeType: 'updated');

            ZoneEvent::query()->create([
                'zone_id' => $zoneId,
                'type' => 'CORRECTION_CONFIG_UPDATED',
                'payload_json' => [
                    'version' => $config->version,
                    'preset_id' => $config->preset_id,
                    'updated_by' => $userId,
                    'hot_reload' => true,
                ],
            ]);

            return $config->loadMissing(['preset', 'updatedBy']);
        });
    }

    public function buildResolvedConfig(
        ?ZoneCorrectionPreset $preset,
        array $baseConfig,
        array $phaseOverrides,
    ): array {
        [$presetBaseConfig, $presetPhaseConfigs] = $this->splitPresetConfig($preset?->config);
        $resolvedBase = ZoneCorrectionConfigCatalog::merge(
            ZoneCorrectionConfigCatalog::defaults(),
            $presetBaseConfig
        );
        $resolvedBase = ZoneCorrectionConfigCatalog::merge($resolvedBase, $baseConfig);

        $resolvedByPhase = [];
        foreach (ZoneCorrectionConfigCatalog::PHASES as $phase) {
            $presetPhaseConfig = is_array($presetPhaseConfigs[$phase] ?? null) ? $presetPhaseConfigs[$phase] : [];
            $override = is_array($phaseOverrides[$phase] ?? null) ? $phaseOverrides[$phase] : [];
            $phaseBase = ZoneCorrectionConfigCatalog::merge($resolvedBase, $presetPhaseConfig);
            $resolvedByPhase[$phase] = ZoneCorrectionConfigCatalog::merge($phaseBase, $override);
        }

        return [
            'base' => $resolvedBase,
            'phases' => $resolvedByPhase,
            'meta' => [
                'preset_id' => $preset?->id,
                'preset_slug' => $preset?->slug,
                'preset_name' => $preset?->name,
            ],
        ];
    }

    public function ensureDefaultForZone(int $zoneId): void
    {
        if (! Schema::hasTable('zone_correction_configs')) {
            return;
        }

        $this->getOrCreateForZone($zoneId);
    }

    public function serializePreset(ZoneCorrectionPreset $preset): array
    {
        return [
            'id' => $preset->id,
            'slug' => $preset->slug,
            'name' => $preset->name,
            'scope' => $preset->scope,
            'is_locked' => $preset->is_locked,
            'is_active' => $preset->is_active,
            'description' => $preset->description,
            'config' => $preset->config ?? [],
            'created_by' => $preset->created_by,
            'updated_by' => $preset->updated_by,
            'updated_at' => optional($preset->updated_at)->toISOString(),
        ];
    }

    private function recordVersion(
        ZoneCorrectionConfig $config,
        ?int $changedBy,
        string $changeType,
    ): void {
        ZoneCorrectionConfigVersion::query()->create([
            'zone_correction_config_id' => $config->id,
            'zone_id' => $config->zone_id,
            'preset_id' => $config->preset_id,
            'version' => $config->version,
            'change_type' => $changeType,
            'base_config' => $config->base_config ?? [],
            'phase_overrides' => $config->phase_overrides ?? [],
            'resolved_config' => $config->resolved_config ?? [],
            'changed_by' => $changedBy,
            'changed_at' => now(),
        ]);
    }

    private function validatePhaseOverrides(array $phaseOverrides): void
    {
        if ($phaseOverrides === []) {
            return;
        }

        if (array_is_list($phaseOverrides)) {
            throw new \InvalidArgumentException('phase_overrides должен быть объектом.');
        }

        foreach ($phaseOverrides as $phase => $override) {
            if (! in_array($phase, ZoneCorrectionConfigCatalog::PHASES, true)) {
                throw new \InvalidArgumentException("Фаза {$phase} не поддерживается. Допустимые значения: ".implode(', ', ZoneCorrectionConfigCatalog::PHASES));
            }
            if (! is_array($override) || array_is_list($override)) {
                throw new \InvalidArgumentException("phase_overrides.{$phase} должен быть объектом.");
            }
            ZoneCorrectionConfigCatalog::validateFragment($override, true);
        }
    }

    private function normalizeStoredOverride(array $referenceBase, array $candidate): array
    {
        try {
            ZoneCorrectionConfigCatalog::validateFragment($candidate, false);
            return ZoneCorrectionConfigCatalog::diff($referenceBase, $candidate);
        } catch (\InvalidArgumentException) {
            ZoneCorrectionConfigCatalog::validateFragment($candidate, true);
            return $candidate;
        }
    }

    private function normalizeStoredPhaseOverrides(
        array $resolvedBase,
        array $presetPhaseConfigs,
        array $phaseOverrides,
    ): array
    {
        $this->validatePhaseOverrides($phaseOverrides);
        $normalized = [];

        foreach ($phaseOverrides as $phase => $override) {
            if (! is_array($override) || array_is_list($override)) {
                continue;
            }
            $phaseReference = ZoneCorrectionConfigCatalog::merge(
                $resolvedBase,
                is_array($presetPhaseConfigs[$phase] ?? null) ? $presetPhaseConfigs[$phase] : []
            );
            $normalized[$phase] = $this->normalizeStoredOverride($phaseReference, $override);
        }

        return $normalized;
    }

    private function splitPresetConfig(mixed $payload): array
    {
        if (! is_array($payload) || array_is_list($payload)) {
            return [[], []];
        }

        $base = $payload['base'] ?? null;
        $phases = $payload['phases'] ?? null;
        if (is_array($base) && ! array_is_list($base)) {
            return [
                $base,
                is_array($phases) && ! array_is_list($phases) ? $phases : [],
            ];
        }

        return [$payload, []];
    }

    private function normalizeExistingUserId(?int $userId): ?int
    {
        if ($userId === null || $userId <= 0) {
            return null;
        }

        return User::query()->whereKey($userId)->exists() ? $userId : null;
    }
}
