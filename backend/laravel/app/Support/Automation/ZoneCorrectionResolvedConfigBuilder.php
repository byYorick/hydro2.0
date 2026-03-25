<?php

namespace App\Support\Automation;

use App\Models\AutomationConfigDocument;
use App\Models\AutomationConfigPreset;
use App\Services\AutomationConfigRegistry;
use App\Services\SystemAutomationSettingsCatalog;
use App\Services\ZoneCorrectionConfigCatalog;

class ZoneCorrectionResolvedConfigBuilder
{
    public function __construct(
        private readonly AutomationConfigRegistry $registry,
    ) {
    }

    /**
     * @param  array<string, mixed>  $payload
     * @return array<string, mixed>
     */
    public function buildFromPayload(array $payload): array
    {
        $presetId = isset($payload['preset_id']) ? (int) $payload['preset_id'] : null;
        $baseConfig = is_array($payload['base_config'] ?? null) && ! array_is_list($payload['base_config'])
            ? $payload['base_config']
            : ZoneCorrectionConfigCatalog::defaults();
        $phaseOverrides = is_array($payload['phase_overrides'] ?? null) && ! array_is_list($payload['phase_overrides'])
            ? $payload['phase_overrides']
            : [];

        return $this->build(
            $this->findPreset($presetId),
            $baseConfig,
            $phaseOverrides
        );
    }

    /**
     * @param  array<string, mixed>  $baseConfig
     * @param  array<string, mixed>  $phaseOverrides
     * @return array<string, mixed>
     */
    public function build(?AutomationConfigPreset $preset, array $baseConfig, array $phaseOverrides): array
    {
        [$presetBaseConfig, $presetPhaseConfigs] = $this->splitPresetConfig($preset?->payload);
        [$baseConfigWithoutPump, $pumpOverride] = $this->splitPumpCalibrationOverride($baseConfig);

        $resolvedBase = is_array($presetBaseConfig) && ! array_is_list($presetBaseConfig)
            ? $presetBaseConfig
            : [];
        $resolvedBase = ZoneCorrectionConfigCatalog::merge($resolvedBase, $baseConfigWithoutPump);
        $resolvedPumpCalibration = $this->resolvePumpCalibrationConfig(
            $this->systemPumpCalibrationDefaults(),
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

    private function findPreset(?int $presetId): ?AutomationConfigPreset
    {
        if ($presetId === null || $presetId <= 0) {
            return null;
        }

        return AutomationConfigPreset::query()
            ->where('namespace', AutomationConfigRegistry::NAMESPACE_ZONE_CORRECTION)
            ->find($presetId);
    }

    /**
     * @return array<string, mixed>
     */
    private function systemPumpCalibrationDefaults(): array
    {
        $document = AutomationConfigDocument::query()
            ->where('namespace', AutomationConfigRegistry::NAMESPACE_SYSTEM_PUMP_CALIBRATION_POLICY)
            ->where('scope_type', AutomationConfigRegistry::SCOPE_SYSTEM)
            ->where('scope_id', 0)
            ->first();
        $payload = $document?->payload;

        return is_array($payload) && ! array_is_list($payload)
            ? $payload
            : $this->registry->defaultPayload(AutomationConfigRegistry::NAMESPACE_SYSTEM_PUMP_CALIBRATION_POLICY);
    }

    /**
     * @return array{0: array<string, mixed>, 1: array<string, mixed>}
     */
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

    /**
     * @param  array<string, mixed>  $baseConfig
     * @return array{0: array<string, mixed>, 1: array<string, mixed>}
     */
    private function splitPumpCalibrationOverride(array $baseConfig): array
    {
        $pumpOverride = [];
        if (isset($baseConfig['pump_calibration']) && is_array($baseConfig['pump_calibration']) && ! array_is_list($baseConfig['pump_calibration'])) {
            $pumpOverride = $baseConfig['pump_calibration'];
        }

        unset($baseConfig['pump_calibration']);

        return [$baseConfig, $pumpOverride];
    }

    /**
     * @param  array<string, mixed>  $defaults
     * @param  array<string, mixed>  $override
     * @return array<string, mixed>
     */
    private function resolvePumpCalibrationConfig(array $defaults, array $override): array
    {
        $resolved = SystemAutomationSettingsCatalog::merge($defaults, $override);
        SystemAutomationSettingsCatalog::validate('pump_calibration', $resolved, false);

        return $resolved;
    }
}
