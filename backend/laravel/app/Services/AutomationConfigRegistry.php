<?php

namespace App\Services;

use App\Support\Automation\ZonePidDefaults;
use App\Support\Automation\ZoneProcessCalibrationDefaults;
use InvalidArgumentException;

class AutomationConfigRegistry
{
    use ValidatesGreenhouseLogicProfile;

    public const SCOPE_SYSTEM = 'system';

    public const SCOPE_GREENHOUSE = 'greenhouse';

    public const SCOPE_ZONE = 'zone';

    public const SCOPE_GROW_CYCLE = 'grow_cycle';

    public const NAMESPACE_SYSTEM_RUNTIME = 'system.runtime';

    public const NAMESPACE_SYSTEM_AUTOMATION_DEFAULTS = 'system.automation_defaults';

    public const NAMESPACE_SYSTEM_COMMAND_TEMPLATES = 'system.command_templates';

    public const NAMESPACE_SYSTEM_PROCESS_CALIBRATION_DEFAULTS = 'system.process_calibration_defaults';

    public const NAMESPACE_SYSTEM_PUMP_CALIBRATION_POLICY = 'system.pump_calibration_policy';

    public const NAMESPACE_SYSTEM_SENSOR_CALIBRATION_POLICY = 'system.sensor_calibration_policy';

    public const NAMESPACE_SYSTEM_ALERT_POLICIES = 'system.alert_policies';

    public const NAMESPACE_SYSTEM_OBSERVABILITY_THRESHOLDS = 'system.observability_thresholds';

    public const NAMESPACE_GREENHOUSE_LOGIC_PROFILE = 'greenhouse.logic_profile';

    public const NAMESPACE_ZONE_LOGIC_PROFILE = 'zone.logic_profile';

    public const NAMESPACE_ZONE_CORRECTION = 'zone.correction';

    public const NAMESPACE_ZONE_PID_PH = 'zone.pid.ph';

    public const NAMESPACE_ZONE_PID_EC = 'zone.pid.ec';

    public const NAMESPACE_ZONE_RUNTIME_TUNING_BUNDLE = 'zone.runtime_tuning_bundle';

    public const NAMESPACE_ZONE_PROCESS_CALIBRATION_GENERIC = 'zone.process_calibration.generic';

    public const NAMESPACE_ZONE_PROCESS_CALIBRATION_SOLUTION_FILL = 'zone.process_calibration.solution_fill';

    public const NAMESPACE_ZONE_PROCESS_CALIBRATION_TANK_RECIRC = 'zone.process_calibration.tank_recirc';

    public const NAMESPACE_ZONE_PROCESS_CALIBRATION_IRRIGATION = 'zone.process_calibration.irrigation';

    public const NAMESPACE_CYCLE_START_SNAPSHOT = 'cycle.start_snapshot';

    public const NAMESPACE_CYCLE_PHASE_OVERRIDES = 'cycle.phase_overrides';

    public const NAMESPACE_CYCLE_MANUAL_OVERRIDES = 'cycle.manual_overrides';

    public const NAMESPACE_CYCLE_CONFIG_OVERRIDES = 'cycle.config_overrides';

    /**
     * @return list<string>
     */
    public function namespaces(): array
    {
        return array_keys($this->definitions());
    }

    /**
     * @return array<string, array<string, mixed>>
     */
    public function definitions(): array
    {
        return [
            self::NAMESPACE_SYSTEM_RUNTIME => [
                'scope_type' => self::SCOPE_SYSTEM,
                'schema_version' => 1,
                'default_payload' => method_exists(AutomationRuntimeConfigService::class, 'defaultSettingsMapStatic')
                    ? AutomationRuntimeConfigService::defaultSettingsMapStatic()
                    : [],
                'required' => true,
            ],
            self::NAMESPACE_SYSTEM_AUTOMATION_DEFAULTS => $this->systemDefinition('automation_defaults'),
            self::NAMESPACE_SYSTEM_COMMAND_TEMPLATES => $this->systemDefinition('automation_command_templates'),
            self::NAMESPACE_SYSTEM_PROCESS_CALIBRATION_DEFAULTS => $this->systemDefinition('process_calibration_defaults'),
            self::NAMESPACE_SYSTEM_PUMP_CALIBRATION_POLICY => $this->systemDefinition('pump_calibration'),
            self::NAMESPACE_SYSTEM_SENSOR_CALIBRATION_POLICY => $this->systemDefinition('sensor_calibration'),
            self::NAMESPACE_SYSTEM_OBSERVABILITY_THRESHOLDS => $this->systemDefinition('observability_thresholds'),
            self::NAMESPACE_SYSTEM_ALERT_POLICIES => [
                'scope_type' => self::SCOPE_SYSTEM,
                'schema_version' => 1,
                'default_payload' => [
                    'ae3_operational_resolution_mode' => AlertPolicyService::MODE_MANUAL_ACK,
                ],
                'required' => true,
            ],
            self::NAMESPACE_GREENHOUSE_LOGIC_PROFILE => [
                'scope_type' => self::SCOPE_GREENHOUSE,
                'schema_version' => 1,
                'default_payload' => [
                    'active_mode' => null,
                    'profiles' => [],
                ],
                'required' => false,
            ],
            self::NAMESPACE_ZONE_LOGIC_PROFILE => [
                'scope_type' => self::SCOPE_ZONE,
                'schema_version' => 1,
                'default_payload' => [
                    'active_mode' => null,
                    'profiles' => [],
                ],
                'required' => true,
            ],
            self::NAMESPACE_ZONE_CORRECTION => [
                'scope_type' => self::SCOPE_ZONE,
                'schema_version' => 1,
                'default_payload' => [
                    'preset_id' => null,
                    'base_config' => ZoneCorrectionConfigCatalog::defaults(),
                    'phase_overrides' => [],
                    'resolved_config' => [],
                ],
                'required' => true,
            ],
            self::NAMESPACE_ZONE_PID_PH => $this->zonePidDefinition('ph'),
            self::NAMESPACE_ZONE_PID_EC => $this->zonePidDefinition('ec'),
            self::NAMESPACE_ZONE_RUNTIME_TUNING_BUNDLE => $this->zoneRuntimeTuningBundleDefinition(),
            self::NAMESPACE_ZONE_PROCESS_CALIBRATION_GENERIC => $this->zoneProcessCalibrationDefinition('generic'),
            self::NAMESPACE_ZONE_PROCESS_CALIBRATION_SOLUTION_FILL => $this->zoneProcessCalibrationDefinition('solution_fill'),
            self::NAMESPACE_ZONE_PROCESS_CALIBRATION_TANK_RECIRC => $this->zoneProcessCalibrationDefinition('tank_recirc'),
            self::NAMESPACE_ZONE_PROCESS_CALIBRATION_IRRIGATION => $this->zoneProcessCalibrationDefinition('irrigation'),
            self::NAMESPACE_CYCLE_START_SNAPSHOT => [
                'scope_type' => self::SCOPE_GROW_CYCLE,
                'schema_version' => 1,
                'default_payload' => [],
                'required' => false,
            ],
            self::NAMESPACE_CYCLE_PHASE_OVERRIDES => [
                'scope_type' => self::SCOPE_GROW_CYCLE,
                'schema_version' => 1,
                'default_payload' => [],
                'required' => false,
            ],
            self::NAMESPACE_CYCLE_MANUAL_OVERRIDES => [
                'scope_type' => self::SCOPE_GROW_CYCLE,
                'schema_version' => 1,
                'default_payload' => [],
                'required' => false,
            ],
            self::NAMESPACE_CYCLE_CONFIG_OVERRIDES => [
                'scope_type' => self::SCOPE_GROW_CYCLE,
                'schema_version' => 1,
                'default_payload' => [],
                'required' => false,
            ],
        ];
    }

    /**
     * @return list<string>
     */
    public function requiredNamespacesForScope(string $scopeType): array
    {
        return array_values(array_filter(
            $this->namespaces(),
            function (string $namespace) use ($scopeType): bool {
                $definition = $this->definition($namespace);

                return $definition['scope_type'] === $scopeType && (bool) ($definition['required'] ?? false);
            }
        ));
    }

    /**
     * @return array<string, mixed>
     */
    public function definition(string $namespace): array
    {
        $definition = $this->definitions()[$namespace] ?? null;
        if (! is_array($definition)) {
            throw new InvalidArgumentException("Unknown automation config namespace {$namespace}.");
        }

        return $definition;
    }

    /**
     * @return array<string, mixed>
     */
    public function defaultPayload(string $namespace): array
    {
        $defaultPayload = $this->definition($namespace)['default_payload'] ?? [];

        return is_array($defaultPayload) ? $defaultPayload : [];
    }

    public function schemaVersion(string $namespace): int
    {
        return (int) ($this->definition($namespace)['schema_version'] ?? 1);
    }

    public function scopeType(string $namespace): string
    {
        return (string) ($this->definition($namespace)['scope_type'] ?? '');
    }

    public function isPresetNamespace(string $namespace): bool
    {
        return in_array($namespace, [
            self::NAMESPACE_ZONE_CORRECTION,
            self::NAMESPACE_ZONE_PID_PH,
            self::NAMESPACE_ZONE_PID_EC,
            self::NAMESPACE_ZONE_PROCESS_CALIBRATION_GENERIC,
            self::NAMESPACE_ZONE_PROCESS_CALIBRATION_SOLUTION_FILL,
            self::NAMESPACE_ZONE_PROCESS_CALIBRATION_TANK_RECIRC,
            self::NAMESPACE_ZONE_PROCESS_CALIBRATION_IRRIGATION,
            self::NAMESPACE_ZONE_RUNTIME_TUNING_BUNDLE,
        ], true);
    }

    public function validate(string $namespace, array $payload, ?string $scopeType = null, ?int $scopeId = null): void
    {
        if ($this->isLegacySystemMappedNamespace($namespace)) {
            $legacyNamespace = $this->authorityToLegacySystemNamespace($namespace);
            SystemAutomationSettingsCatalog::validate($legacyNamespace, $payload, false);

            return;
        }

        switch ($namespace) {
            case self::NAMESPACE_SYSTEM_RUNTIME:
                $this->validateRuntimePayload($payload);

                return;

            case self::NAMESPACE_SYSTEM_ALERT_POLICIES:
                $this->validateAlertPoliciesPayload($payload);

                return;

            case self::NAMESPACE_ZONE_CORRECTION:
                $this->validateZoneCorrectionPayload($payload);

                return;

            case self::NAMESPACE_ZONE_PID_PH:
                ZonePidPayloadValidator::validate($payload, 'ph');

                return;

            case self::NAMESPACE_ZONE_PID_EC:
                ZonePidPayloadValidator::validate($payload, 'ec');

                return;

            case self::NAMESPACE_ZONE_RUNTIME_TUNING_BUNDLE:
                $this->validateRuntimeTuningBundlePayload($payload);

                return;

            case self::NAMESPACE_ZONE_LOGIC_PROFILE:
                $this->validateLogicProfilePayload($payload);

                return;

            case self::NAMESPACE_GREENHOUSE_LOGIC_PROFILE:
                $this->validateGreenhouseLogicProfilePayload(
                    $payload,
                    $scopeType === self::SCOPE_GREENHOUSE ? $scopeId : null
                );

                return;

            case self::NAMESPACE_ZONE_PROCESS_CALIBRATION_GENERIC:
            case self::NAMESPACE_ZONE_PROCESS_CALIBRATION_SOLUTION_FILL:
            case self::NAMESPACE_ZONE_PROCESS_CALIBRATION_TANK_RECIRC:
            case self::NAMESPACE_ZONE_PROCESS_CALIBRATION_IRRIGATION:
                $this->validateProcessCalibrationPayload($payload);

                return;

            case self::NAMESPACE_CYCLE_START_SNAPSHOT:
            case self::NAMESPACE_CYCLE_PHASE_OVERRIDES:
            case self::NAMESPACE_CYCLE_CONFIG_OVERRIDES:
                if ($payload !== [] && array_is_list($payload)) {
                    throw new InvalidArgumentException("Payload for {$namespace} must be an object.");
                }

                return;

            case self::NAMESPACE_CYCLE_MANUAL_OVERRIDES:
                if (! array_is_list($payload)) {
                    throw new InvalidArgumentException('cycle.manual_overrides must be an array.');
                }

                return;
        }
    }

    public function authorityToLegacySystemNamespace(string $namespace): ?string
    {
        return match ($namespace) {
            self::NAMESPACE_SYSTEM_AUTOMATION_DEFAULTS => 'automation_defaults',
            self::NAMESPACE_SYSTEM_COMMAND_TEMPLATES => 'automation_command_templates',
            self::NAMESPACE_SYSTEM_PROCESS_CALIBRATION_DEFAULTS => 'process_calibration_defaults',
            self::NAMESPACE_SYSTEM_PUMP_CALIBRATION_POLICY => 'pump_calibration',
            self::NAMESPACE_SYSTEM_SENSOR_CALIBRATION_POLICY => 'sensor_calibration',
            self::NAMESPACE_SYSTEM_OBSERVABILITY_THRESHOLDS => 'observability_thresholds',
            default => null,
        };
    }

    public function legacySystemNamespaceToAuthority(string $namespace): ?string
    {
        return match ($namespace) {
            'automation_defaults' => self::NAMESPACE_SYSTEM_AUTOMATION_DEFAULTS,
            'automation_command_templates' => self::NAMESPACE_SYSTEM_COMMAND_TEMPLATES,
            'process_calibration_defaults' => self::NAMESPACE_SYSTEM_PROCESS_CALIBRATION_DEFAULTS,
            'pump_calibration' => self::NAMESPACE_SYSTEM_PUMP_CALIBRATION_POLICY,
            'sensor_calibration' => self::NAMESPACE_SYSTEM_SENSOR_CALIBRATION_POLICY,
            'observability_thresholds' => self::NAMESPACE_SYSTEM_OBSERVABILITY_THRESHOLDS,
            default => null,
        };
    }

    public function pidNamespace(string $type): string
    {
        return $type === 'ph' ? self::NAMESPACE_ZONE_PID_PH : self::NAMESPACE_ZONE_PID_EC;
    }

    public function processCalibrationNamespaceForMode(string $mode): string
    {
        return match ($mode) {
            'generic' => self::NAMESPACE_ZONE_PROCESS_CALIBRATION_GENERIC,
            'solution_fill' => self::NAMESPACE_ZONE_PROCESS_CALIBRATION_SOLUTION_FILL,
            'tank_recirc' => self::NAMESPACE_ZONE_PROCESS_CALIBRATION_TANK_RECIRC,
            'irrigation' => self::NAMESPACE_ZONE_PROCESS_CALIBRATION_IRRIGATION,
            default => throw new InvalidArgumentException("Unsupported process calibration mode {$mode}."),
        };
    }

    private function isLegacySystemMappedNamespace(string $namespace): bool
    {
        return $this->authorityToLegacySystemNamespace($namespace) !== null;
    }

    /**
     * @return array<string, mixed>
     */
    private function systemDefinition(string $legacyNamespace): array
    {
        return [
            'scope_type' => self::SCOPE_SYSTEM,
            'schema_version' => 1,
            'default_payload' => SystemAutomationSettingsCatalog::defaults($legacyNamespace),
            'required' => true,
        ];
    }

    /**
     * @return array<string, mixed>
     */
    private function zonePidDefinition(string $type): array
    {
        return [
            'scope_type' => self::SCOPE_ZONE,
            'schema_version' => 1,
            'default_payload' => ZonePidDefaults::forType($type),
            'required' => true,
        ];
    }

    /**
     * @return array<string, mixed>
     */
    private function zoneRuntimeTuningBundleDefinition(): array
    {
        $processCalibration = [];
        foreach (['generic', 'solution_fill', 'tank_recirc', 'irrigation'] as $mode) {
            $processCalibration[$mode] = array_merge(
                ZoneProcessCalibrationDefaults::forMode($mode),
                [
                    'mode' => $mode,
                    'source' => 'system_default',
                    'meta' => [],
                ]
            );
        }

        $pid = [
            'ph' => ZonePidDefaults::forType('ph'),
            'ec' => ZonePidDefaults::forType('ec'),
        ];

        $systemPreset = [
            'key' => 'system_default',
            'name' => 'Системный preset',
            'description' => 'Канонические стартовые значения process calibration и PID для зоны.',
            'process_calibration' => $processCalibration,
            'pid' => $pid,
        ];

        return [
            'scope_type' => self::SCOPE_ZONE,
            'schema_version' => 1,
            'default_payload' => [
                'selected_preset_key' => 'system_default',
                'presets' => [$systemPreset],
                'advanced_overrides' => [],
                'resolved_preview' => [
                    'process_calibration' => $processCalibration,
                    'pid' => $pid,
                ],
            ],
            'required' => true,
        ];
    }

    /**
     * @return array<string, mixed>
     */
    private function zoneProcessCalibrationDefinition(string $mode): array
    {
        return [
            'scope_type' => self::SCOPE_ZONE,
            'schema_version' => 1,
            'default_payload' => array_merge(
                ZoneProcessCalibrationDefaults::forMode($mode),
                [
                    'mode' => $mode,
                    'source' => 'system_default',
                    'meta' => [],
                ]
            ),
            'required' => true,
        ];
    }

    private function validateRuntimePayload(array $payload): void
    {
        if (array_is_list($payload)) {
            throw new InvalidArgumentException('system.runtime must be an object.');
        }

        foreach ($payload as $key => $_value) {
            if (! is_string($key) || trim($key) === '') {
                throw new InvalidArgumentException('system.runtime keys must be non-empty strings.');
            }
        }
    }

    private function validateAlertPoliciesPayload(array $payload): void
    {
        if (array_is_list($payload)) {
            throw new InvalidArgumentException('system.alert_policies must be an object.');
        }

        $allowedKeys = ['ae3_operational_resolution_mode'];
        foreach (array_keys($payload) as $key) {
            if (! is_string($key) || ! in_array($key, $allowedKeys, true)) {
                throw new InvalidArgumentException("system.alert_policies.{$key} is not supported.");
            }
        }

        $mode = $payload['ae3_operational_resolution_mode'] ?? null;
        if (! is_string($mode) || ! in_array($mode, AlertPolicyService::MODES, true)) {
            throw new InvalidArgumentException(
                'system.alert_policies.ae3_operational_resolution_mode must be one of: '
                .implode(', ', AlertPolicyService::MODES)
            );
        }
    }

    private function validateZoneCorrectionPayload(array $payload): void
    {
        $baseConfig = $payload['base_config'] ?? [];
        $phaseOverrides = $payload['phase_overrides'] ?? [];

        if (! is_array($baseConfig) || ($baseConfig !== [] && array_is_list($baseConfig))) {
            throw new InvalidArgumentException('zone.correction.base_config must be an object.');
        }
        if (! is_array($phaseOverrides) || ($phaseOverrides !== [] && array_is_list($phaseOverrides))) {
            throw new InvalidArgumentException('zone.correction.phase_overrides must be an object.');
        }

        ZoneCorrectionConfigCatalog::validateFragment($baseConfig, false);
        foreach ($phaseOverrides as $phase => $phaseConfig) {
            if (! in_array($phase, ZoneCorrectionConfigCatalog::PHASES, true)) {
                throw new InvalidArgumentException("Unsupported correction phase {$phase}.");
            }
            if (! is_array($phaseConfig) || array_is_list($phaseConfig)) {
                throw new InvalidArgumentException("Correction phase {$phase} must be an object.");
            }
            // Phase overrides are intentionally sparse diffs over base_config —
            // полный merge делает resolver при pull; требовать full payload здесь
            // ломает Phase 6.2 live-edit (patch timing.* без остальных timing-полей).
            ZoneCorrectionConfigCatalog::validateFragment($phaseConfig, true);
        }
    }

    private function validateRuntimeTuningBundlePayload(array $payload): void
    {
        if (array_is_list($payload)) {
            throw new InvalidArgumentException('zone.runtime_tuning_bundle must be an object.');
        }

        $selectedPresetKey = trim((string) ($payload['selected_preset_key'] ?? ''));
        if ($selectedPresetKey === '') {
            throw new InvalidArgumentException('zone.runtime_tuning_bundle.selected_preset_key is required.');
        }

        $presets = $payload['presets'] ?? null;
        if (! is_array($presets) || ! array_is_list($presets) || $presets === []) {
            throw new InvalidArgumentException('zone.runtime_tuning_bundle.presets must be a non-empty array.');
        }

        $presetKeys = [];
        foreach ($presets as $index => $preset) {
            if (! is_array($preset) || array_is_list($preset)) {
                throw new InvalidArgumentException("zone.runtime_tuning_bundle.presets.{$index} must be an object.");
            }

            $key = trim((string) ($preset['key'] ?? ''));
            if ($key === '') {
                throw new InvalidArgumentException("zone.runtime_tuning_bundle.presets.{$index}.key is required.");
            }
            $presetKeys[] = $key;

            if (trim((string) ($preset['name'] ?? '')) === '') {
                throw new InvalidArgumentException("zone.runtime_tuning_bundle.presets.{$index}.name is required.");
            }

            $processCalibration = $preset['process_calibration'] ?? null;
            if (! is_array($processCalibration) || array_is_list($processCalibration)) {
                throw new InvalidArgumentException("zone.runtime_tuning_bundle.presets.{$index}.process_calibration must be an object.");
            }

            foreach (['generic', 'solution_fill', 'tank_recirc', 'irrigation'] as $mode) {
                $modePayload = $processCalibration[$mode] ?? null;
                if (! is_array($modePayload) || array_is_list($modePayload)) {
                    throw new InvalidArgumentException("zone.runtime_tuning_bundle.presets.{$index}.process_calibration.{$mode} must be an object.");
                }
                $this->validateProcessCalibrationPayload($modePayload);
            }

            $pid = $preset['pid'] ?? null;
            if (! is_array($pid) || array_is_list($pid)) {
                throw new InvalidArgumentException("zone.runtime_tuning_bundle.presets.{$index}.pid must be an object.");
            }
            ZonePidPayloadValidator::validate(is_array($pid['ph'] ?? null) ? $pid['ph'] : [], 'ph');
            ZonePidPayloadValidator::validate(is_array($pid['ec'] ?? null) ? $pid['ec'] : [], 'ec');
        }

        if (! in_array($selectedPresetKey, $presetKeys, true)) {
            throw new InvalidArgumentException('zone.runtime_tuning_bundle.selected_preset_key must reference an existing preset.');
        }

        $advancedOverrides = $payload['advanced_overrides'] ?? [];
        if (! is_array($advancedOverrides) || ($advancedOverrides !== [] && array_is_list($advancedOverrides))) {
            throw new InvalidArgumentException('zone.runtime_tuning_bundle.advanced_overrides must be an object.');
        }

        $resolvedPreview = $payload['resolved_preview'] ?? [];
        if (! is_array($resolvedPreview) || ($resolvedPreview !== [] && array_is_list($resolvedPreview))) {
            throw new InvalidArgumentException('zone.runtime_tuning_bundle.resolved_preview must be an object.');
        }
    }

    private function validateLogicProfilePayload(array $payload): void
    {
        if (array_is_list($payload)) {
            throw new InvalidArgumentException('zone.logic_profile must be an object.');
        }

        $profiles = $payload['profiles'] ?? [];
        if (! is_array($profiles) || ($profiles !== [] && array_is_list($profiles))) {
            throw new InvalidArgumentException('zone.logic_profile.profiles must be an object.');
        }

        foreach ($profiles as $mode => $profile) {
            if (! in_array($mode, ZoneLogicProfileCatalog::allowedModes(), true)) {
                throw new InvalidArgumentException("Unsupported logic profile mode {$mode}.");
            }
            if (! is_array($profile) || array_is_list($profile)) {
                throw new InvalidArgumentException("Profile {$mode} must be an object.");
            }
            $this->validateIrrigationDecisionStrategy($profile, (string) $mode);
        }
    }

    /**
     * Проверяется только явная стратегия. lookback, hysteresis и command_plans не отвергаются.
     *
     * @param  array<string, mixed>  $profile
     */
    private function validateIrrigationDecisionStrategy(array $profile, string $mode): void
    {
        $decision = data_get($profile, 'subsystems.irrigation.decision');
        if (! is_array($decision) || ! array_key_exists('strategy', $decision) || $decision['strategy'] === null) {
            return;
        }

        $strategy = $decision['strategy'];
        if (! is_string($strategy) || ! in_array($strategy, ['task', 'smart_soil_v1'], true)) {
            throw new InvalidArgumentException(
                "zone.logic_profile.profiles.{$mode}.subsystems.irrigation.decision.strategy must be task or smart_soil_v1."
            );
        }
    }

    private function validateProcessCalibrationPayload(array $payload): void
    {
        if (array_is_list($payload)) {
            throw new InvalidArgumentException('Process calibration payload must be an object.');
        }

        $hasPrimaryGain = false;
        foreach (['ec_gain_per_ml', 'ph_up_gain_per_ml', 'ph_down_gain_per_ml'] as $key) {
            if (array_key_exists($key, $payload) && $payload[$key] !== null && is_numeric($payload[$key])) {
                $hasPrimaryGain = true;
            }
        }

        if (! $hasPrimaryGain) {
            throw new InvalidArgumentException('Нужно задать хотя бы один primary gain: ec_gain_per_ml, ph_up_gain_per_ml или ph_down_gain_per_ml.');
        }
    }
}
