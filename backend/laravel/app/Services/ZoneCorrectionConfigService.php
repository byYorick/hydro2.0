<?php

namespace App\Services;

use App\Models\AutomationConfigPreset;
use App\Models\AutomationConfigVersion;
use App\Models\User;
use App\Models\Zone;
use App\Models\ZoneCorrectionConfig;
use App\Models\ZoneCorrectionConfigVersion;
use App\Models\ZoneEvent;
use Illuminate\Support\Facades\DB;

class ZoneCorrectionConfigService
{
    public function __construct(
        private readonly AutomationConfigDocumentService $documents,
        private readonly AutomationConfigPresetService $presets,
    ) {
    }

    public function getOrCreateForZone(Zone|int $zone): ZoneCorrectionConfig
    {
        $zoneId = $zone instanceof Zone ? $zone->id : (int) $zone;
        $this->documents->ensureZoneDefaults($zoneId);
        $document = $this->documents->getDocument(
            AutomationConfigRegistry::NAMESPACE_ZONE_CORRECTION,
            AutomationConfigRegistry::SCOPE_ZONE,
            $zoneId,
            true
        );

        return $this->makeTransientConfig(
            $zoneId,
            is_array($document?->payload) ? $document->payload : [],
            $document?->updated_by,
            $document?->updated_at,
            $this->latestVersionNumber($zoneId),
            $document?->id
        );
    }

    public function getResponsePayload(Zone|int $zone): array
    {
        $config = $this->getOrCreateForZone($zone);
        $pumpDefaults = $this->documents->getSystemPayloadByLegacyNamespace('pump_calibration', true);
        $pumpOverride = $this->extractPumpCalibrationOverride($config->base_config ?? []);
        $resolvedConfig = $config->resolved_config;
        if (! is_array($resolvedConfig) || array_is_list($resolvedConfig)) {
            $resolvedConfig = [];
        }
        if ($pumpOverride !== []) {
            // Validate the stored zone-level diff against current system defaults
            // without mutating the resolved_config payload returned from the DB.
            $this->resolvePumpCalibrationConfig($pumpDefaults, $pumpOverride);
        }

        return [
            'id' => $config->id,
            'zone_id' => $config->zone_id,
            'preset' => $config->preset ? $this->serializePreset($config->preset) : null,
            'base_config' => $config->base_config ?? [],
            'phase_overrides' => $config->phase_overrides ?? [],
            'resolved_config' => $resolvedConfig,
            'version' => $config->version,
            'updated_at' => optional($config->updated_at)->toISOString(),
            'updated_by' => $config->updated_by,
            'last_applied_at' => optional($config->last_applied_at)->toISOString(),
            'last_applied_version' => $config->last_applied_version,
            'meta' => [
                'phases' => ZoneCorrectionConfigCatalog::PHASES,
                'defaults' => ZoneCorrectionConfigCatalog::defaults(),
                'field_catalog' => ZoneCorrectionConfigCatalog::fieldCatalog(),
                'pump_calibration_defaults' => $pumpDefaults,
                'pump_calibration_field_catalog' => SystemAutomationSettingsCatalog::fieldCatalog('pump_calibration'),
            ],
        ];
    }

    public function listVersions(Zone|int $zone): array
    {
        $zoneId = $zone instanceof Zone ? $zone->id : (int) $zone;

        return AutomationConfigVersion::query()
            ->with('changedBy')
            ->where('namespace', AutomationConfigRegistry::NAMESPACE_ZONE_CORRECTION)
            ->where('scope_type', AutomationConfigRegistry::SCOPE_ZONE)
            ->where('scope_id', $zoneId)
            ->orderByDesc('id')
            ->get()
            ->map(function (AutomationConfigVersion $version): array {
                $payload = is_array($version->payload) ? $version->payload : [];
                $presetId = isset($payload['preset_id']) ? (int) $payload['preset_id'] : null;
                $preset = $presetId ? $this->findCorrectionPreset($presetId) : null;

                return [
                    'id' => $version->id,
                    'version' => (int) $version->id,
                    'change_type' => (string) ($version->source ?? 'updated'),
                    'preset' => $preset ? $this->serializePreset($preset) : null,
                    'changed_by' => $version->changed_by,
                    'changed_at' => optional($version->changed_at)->toISOString(),
                    'base_config' => is_array($payload['base_config'] ?? null) ? $payload['base_config'] : [],
                    'phase_overrides' => is_array($payload['phase_overrides'] ?? null) ? $payload['phase_overrides'] : [],
                    'resolved_config' => is_array($payload['resolved_config'] ?? null) ? $payload['resolved_config'] : [],
                ];
            })
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
            $preset = $this->presets->findOrFail((int) $presetId, AutomationConfigRegistry::NAMESPACE_ZONE_CORRECTION);
        }

        return DB::transaction(function () use ($zoneId, $preset, $baseConfig, $phaseOverrides, $userId): ZoneCorrectionConfig {
            $pumpDefaults = $this->documents->getSystemPayloadByLegacyNamespace('pump_calibration', true);
            [$baseConfigWithoutPump, $pumpOverride] = $this->splitPumpCalibrationOverride($baseConfig);
            SystemAutomationSettingsCatalog::validate('pump_calibration', $pumpOverride, true);
            [$presetBaseConfig, $presetPhaseConfigs] = $this->splitPresetConfig($preset?->payload);
            $presetBase = is_array($presetBaseConfig) && ! array_is_list($presetBaseConfig)
                ? $presetBaseConfig
                : [];
            $storedBaseConfig = $this->normalizeStoredOverride($presetBase, $baseConfigWithoutPump);
            if ($pumpOverride !== []) {
                $storedBaseConfig['pump_calibration'] = SystemAutomationSettingsCatalog::diff(
                    $pumpDefaults,
                    $this->resolvePumpCalibrationConfig($pumpDefaults, $pumpOverride)
                );
            }
            $resolvedBase = ZoneCorrectionConfigCatalog::merge($presetBase, $baseConfigWithoutPump);
            $storedPhaseOverrides = $this->normalizeStoredPhaseOverrides(
                resolvedBase: $resolvedBase,
                presetPhaseConfigs: $presetPhaseConfigs,
                phaseOverrides: $phaseOverrides,
            );

            $resolved = $this->buildResolvedConfig(
                preset: $preset,
                baseConfig: $storedBaseConfig,
                phaseOverrides: $storedPhaseOverrides,
            );
            if ($preset !== null || $this->hasNonPumpCorrectionData($storedBaseConfig, $storedPhaseOverrides)) {
                ZoneCorrectionConfigCatalog::validateResolvedConfig($resolved);
            }

            $document = $this->documents->upsertDocument(
                AutomationConfigRegistry::NAMESPACE_ZONE_CORRECTION,
                AutomationConfigRegistry::SCOPE_ZONE,
                $zoneId,
                [
                    'preset_id' => $preset?->id,
                    'base_config' => $storedBaseConfig,
                    'phase_overrides' => $storedPhaseOverrides,
                    'resolved_config' => $resolved,
                ],
                $userId,
                'zone_correction_config'
            );

            ZoneEvent::query()->create([
                'zone_id' => $zoneId,
                'type' => 'CORRECTION_CONFIG_UPDATED',
                'payload_json' => [
                    'version' => $this->latestVersionNumber($zoneId),
                    'preset_id' => $preset?->id,
                    'updated_by' => $userId,
                    'hot_reload' => true,
                ],
            ]);

            return $this->makeTransientConfig(
                $zoneId,
                is_array($document->payload) ? $document->payload : [],
                $document->updated_by,
                $document->updated_at,
                $this->latestVersionNumber($zoneId),
                $document->id
            );
        });
    }

    public function buildResolvedConfig(
        ?AutomationConfigPreset $preset,
        array $baseConfig,
        array $phaseOverrides,
    ): array {
        [$presetBaseConfig, $presetPhaseConfigs] = $this->splitPresetConfig($preset?->payload);
        [$baseConfigWithoutPump, $pumpOverride] = $this->splitPumpCalibrationOverride($baseConfig);
        $resolvedBase = is_array($presetBaseConfig) && ! array_is_list($presetBaseConfig)
            ? $presetBaseConfig
            : [];
        $resolvedBase = ZoneCorrectionConfigCatalog::merge($resolvedBase, $baseConfigWithoutPump);
        $resolvedPumpCalibration = $this->resolvePumpCalibrationConfig(
            $this->documents->getSystemPayloadByLegacyNamespace('pump_calibration', true),
            $pumpOverride,
        );

        $resolvedByPhase = [];
        foreach (ZoneCorrectionConfigCatalog::PHASES as $phase) {
            $presetPhaseConfig = is_array($presetPhaseConfigs[$phase] ?? null) ? $presetPhaseConfigs[$phase] : [];
            $override = is_array($phaseOverrides[$phase] ?? null) ? $phaseOverrides[$phase] : [];
            $phaseBase = ZoneCorrectionConfigCatalog::merge($resolvedBase, $presetPhaseConfig);
            $resolvedByPhase[$phase] = ZoneCorrectionConfigCatalog::merge($phaseBase, $override);
        }

        return [
            'base' => $resolvedBase,
            'pump_calibration' => $resolvedPumpCalibration,
            'phases' => $resolvedByPhase,
            'meta' => [
                'preset_id' => $preset?->id,
                'preset_slug' => $preset?->slug,
                'preset_name' => $preset?->name,
            ],
        ];
    }

    private function hasNonPumpCorrectionData(array $baseConfig, array $phaseOverrides): bool
    {
        $baseWithoutPump = $baseConfig;
        unset($baseWithoutPump['pump_calibration']);

        if ($baseWithoutPump !== []) {
            return true;
        }

        foreach ($phaseOverrides as $override) {
            if (is_array($override) && $override !== []) {
                return true;
            }
        }

        return false;
    }

    public function ensureDefaultForZone(int $zoneId): void
    {
        $this->documents->ensureZoneDefaults($zoneId);
        $this->resolveMissingBootstrapAlert($zoneId);
    }

    public function serializePreset(AutomationConfigPreset $preset): array
    {
        return [
            'id' => $preset->id,
            'slug' => $preset->slug,
            'name' => $preset->name,
            'scope' => $preset->scope,
            'is_locked' => $preset->is_locked,
            'is_active' => true,
            'description' => $preset->description,
            'config' => $preset->payload ?? [],
            'created_by' => null,
            'updated_by' => $preset->updated_by,
            'updated_at' => optional($preset->updated_at)->toISOString(),
        ];
    }

    /**
     * @param  array<string, mixed>  $payload
     */
    private function makeTransientConfig(
        int $zoneId,
        array $payload,
        ?int $updatedBy,
        mixed $updatedAt,
        int $version,
        ?int $documentId = null,
    ): ZoneCorrectionConfig {
        $presetId = isset($payload['preset_id']) ? (int) $payload['preset_id'] : null;
        $config = new ZoneCorrectionConfig();
        $config->forceFill([
            'id' => $documentId,
            'zone_id' => $zoneId,
            'preset_id' => $presetId,
            'base_config' => is_array($payload['base_config'] ?? null) ? $payload['base_config'] : [],
            'phase_overrides' => is_array($payload['phase_overrides'] ?? null) ? $payload['phase_overrides'] : [],
            'resolved_config' => is_array($payload['resolved_config'] ?? null) ? $payload['resolved_config'] : [],
            'version' => $version,
            'updated_by' => $updatedBy,
            'updated_at' => $updatedAt,
            'last_applied_at' => null,
            'last_applied_version' => null,
        ]);

        if ($presetId) {
            $preset = $this->findCorrectionPreset($presetId);
            if ($preset) {
                $config->setRelation('preset', $preset);
            }
        }

        return $config;
    }

    private function latestVersionNumber(int $zoneId): int
    {
        return (int) (AutomationConfigVersion::query()
            ->where('namespace', AutomationConfigRegistry::NAMESPACE_ZONE_CORRECTION)
            ->where('scope_type', AutomationConfigRegistry::SCOPE_ZONE)
            ->where('scope_id', $zoneId)
            ->max('id') ?? 0);
    }

    private function findCorrectionPreset(int $presetId): ?AutomationConfigPreset
    {
        return AutomationConfigPreset::query()
            ->where('namespace', AutomationConfigRegistry::NAMESPACE_ZONE_CORRECTION)
            ->find($presetId);
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

    private function createBootstrapPlaceholderConfig(int $zoneId): ZoneCorrectionConfig
    {
        $resolved = $this->buildResolvedConfig(
            preset: null,
            baseConfig: [],
            phaseOverrides: [],
        );

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

        return $created;
    }

    private function createBootstrapDefaultConfig(int $zoneId): ZoneCorrectionConfig
    {
        $defaults = ZoneCorrectionConfigCatalog::defaults();
        $resolved = $this->buildResolvedConfig(
            preset: null,
            baseConfig: $defaults,
            phaseOverrides: [],
        );

        $created = ZoneCorrectionConfig::query()->create([
            'zone_id' => $zoneId,
            'preset_id' => null,
            'base_config' => $defaults,
            'phase_overrides' => [],
            'resolved_config' => $resolved,
            'version' => 1,
            'updated_by' => null,
        ]);

        $this->recordVersion($created, changedBy: null, changeType: 'bootstrap');

        return $created;
    }

    private function resolveMissingBootstrapAlert(int $zoneId): void
    {
        app(AlertService::class)->resolveByCode($zoneId, 'biz_zone_correction_config_missing', [
            'resolved_by' => 'zone_correction_bootstrap',
            'resolved_via' => 'auto',
            'reason' => 'correction_config_bootstrap_defaults_applied',
        ]);
    }

    private function isUninitializedBootstrapConfig(ZoneCorrectionConfig $config): bool
    {
        if ((int) $config->preset_id !== 0) {
            return false;
        }

        $baseConfig = is_array($config->base_config) && ! array_is_list($config->base_config)
            ? $config->base_config
            : [];
        $phaseOverrides = is_array($config->phase_overrides) && ! array_is_list($config->phase_overrides)
            ? $config->phase_overrides
            : [];
        $resolvedConfig = is_array($config->resolved_config) && ! array_is_list($config->resolved_config)
            ? $config->resolved_config
            : [];
        $resolvedBase = is_array($resolvedConfig['base'] ?? null) && ! array_is_list($resolvedConfig['base'])
            ? $resolvedConfig['base']
            : [];

        return $baseConfig === [] && $phaseOverrides === [] && $resolvedBase === [];
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
        unset($candidate['pump_calibration']);

        if ($this->hasCompleteOverrideContract($referenceBase, $candidate)) {
            ZoneCorrectionConfigCatalog::validateFragment($candidate, false);

            return ZoneCorrectionConfigCatalog::diff($referenceBase, $candidate);
        }

        ZoneCorrectionConfigCatalog::validateFragment($candidate, true);

        return $candidate;
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

    private function splitPumpCalibrationOverride(array $baseConfig): array
    {
        $pumpOverride = [];
        if (isset($baseConfig['pump_calibration']) && is_array($baseConfig['pump_calibration']) && ! array_is_list($baseConfig['pump_calibration'])) {
            $pumpOverride = $baseConfig['pump_calibration'];
        }

        unset($baseConfig['pump_calibration']);

        return [$baseConfig, $pumpOverride];
    }

    private function extractPumpCalibrationOverride(array $baseConfig): array
    {
        return isset($baseConfig['pump_calibration']) && is_array($baseConfig['pump_calibration']) && ! array_is_list($baseConfig['pump_calibration'])
            ? $baseConfig['pump_calibration']
            : [];
    }

    private function resolvePumpCalibrationConfig(array $defaults, array $override): array
    {
        $resolved = SystemAutomationSettingsCatalog::merge($defaults, $override);
        SystemAutomationSettingsCatalog::validate('pump_calibration', $resolved, false);

        return $resolved;
    }

    private function hasCompleteOverrideContract(array $referenceBase, array $candidate): bool
    {
        foreach ($referenceBase as $key => $referenceValue) {
            if (! array_key_exists($key, $candidate)) {
                return false;
            }

            if (
                is_array($referenceValue)
                && ! array_is_list($referenceValue)
                && ! is_array($candidate[$key])
            ) {
                return false;
            }

            if (
                is_array($referenceValue)
                && ! array_is_list($referenceValue)
                && ! $this->hasCompleteOverrideContract($referenceValue, $candidate[$key])
            ) {
                return false;
            }
        }

        return true;
    }
}
