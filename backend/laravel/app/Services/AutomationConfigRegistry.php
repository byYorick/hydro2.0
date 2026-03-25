<?php

namespace App\Services;

use InvalidArgumentException;

class AutomationConfigRegistry
{
    public const SCOPE_SYSTEM = 'system';
    public const SCOPE_GREENHOUSE = 'greenhouse';
    public const SCOPE_ZONE = 'zone';
    public const SCOPE_GROW_CYCLE = 'grow_cycle';

    public const NAMESPACE_SYSTEM_RUNTIME = 'system.runtime';
    public const NAMESPACE_SYSTEM_AUTOMATION_DEFAULTS = 'system.automation_defaults';
    public const NAMESPACE_SYSTEM_COMMAND_TEMPLATES = 'system.command_templates';
    public const NAMESPACE_SYSTEM_PROCESS_CALIBRATION_DEFAULTS = 'system.process_calibration_defaults';
    public const NAMESPACE_SYSTEM_PID_DEFAULTS_PH = 'system.pid_defaults.ph';
    public const NAMESPACE_SYSTEM_PID_DEFAULTS_EC = 'system.pid_defaults.ec';
    public const NAMESPACE_SYSTEM_PUMP_CALIBRATION_POLICY = 'system.pump_calibration_policy';
    public const NAMESPACE_SYSTEM_SENSOR_CALIBRATION_POLICY = 'system.sensor_calibration_policy';
    public const NAMESPACE_GREENHOUSE_LOGIC_PROFILE = 'greenhouse.logic_profile';
    public const NAMESPACE_ZONE_LOGIC_PROFILE = 'zone.logic_profile';
    public const NAMESPACE_ZONE_CORRECTION = 'zone.correction';
    public const NAMESPACE_ZONE_PID_PH = 'zone.pid.ph';
    public const NAMESPACE_ZONE_PID_EC = 'zone.pid.ec';
    public const NAMESPACE_ZONE_PROCESS_CALIBRATION_GENERIC = 'zone.process_calibration.generic';
    public const NAMESPACE_ZONE_PROCESS_CALIBRATION_SOLUTION_FILL = 'zone.process_calibration.solution_fill';
    public const NAMESPACE_ZONE_PROCESS_CALIBRATION_TANK_RECIRC = 'zone.process_calibration.tank_recirc';
    public const NAMESPACE_ZONE_PROCESS_CALIBRATION_IRRIGATION = 'zone.process_calibration.irrigation';
    public const NAMESPACE_CYCLE_START_SNAPSHOT = 'cycle.start_snapshot';
    public const NAMESPACE_CYCLE_PHASE_OVERRIDES = 'cycle.phase_overrides';
    public const NAMESPACE_CYCLE_MANUAL_OVERRIDES = 'cycle.manual_overrides';

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
            self::NAMESPACE_SYSTEM_PID_DEFAULTS_PH => $this->systemDefinition('pid_defaults_ph'),
            self::NAMESPACE_SYSTEM_PID_DEFAULTS_EC => $this->systemDefinition('pid_defaults_ec'),
            self::NAMESPACE_SYSTEM_PUMP_CALIBRATION_POLICY => $this->systemDefinition('pump_calibration'),
            self::NAMESPACE_SYSTEM_SENSOR_CALIBRATION_POLICY => $this->systemDefinition('sensor_calibration'),
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
        ], true);
    }

    public function validate(string $namespace, array $payload): void
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

            case self::NAMESPACE_ZONE_CORRECTION:
                $this->validateZoneCorrectionPayload($payload);
                return;

            case self::NAMESPACE_ZONE_PID_PH:
                $this->validatePidPayload($payload, 'ph');
                return;

            case self::NAMESPACE_ZONE_PID_EC:
                $this->validatePidPayload($payload, 'ec');
                return;

            case self::NAMESPACE_ZONE_LOGIC_PROFILE:
                $this->validateLogicProfilePayload($payload);
                return;

            case self::NAMESPACE_GREENHOUSE_LOGIC_PROFILE:
                $this->validateGreenhouseLogicProfilePayload($payload);
                return;

            case self::NAMESPACE_ZONE_PROCESS_CALIBRATION_GENERIC:
            case self::NAMESPACE_ZONE_PROCESS_CALIBRATION_SOLUTION_FILL:
            case self::NAMESPACE_ZONE_PROCESS_CALIBRATION_TANK_RECIRC:
            case self::NAMESPACE_ZONE_PROCESS_CALIBRATION_IRRIGATION:
                $this->validateProcessCalibrationPayload($payload);
                return;

            case self::NAMESPACE_CYCLE_START_SNAPSHOT:
            case self::NAMESPACE_CYCLE_PHASE_OVERRIDES:
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
            self::NAMESPACE_SYSTEM_PID_DEFAULTS_PH => 'pid_defaults_ph',
            self::NAMESPACE_SYSTEM_PID_DEFAULTS_EC => 'pid_defaults_ec',
            self::NAMESPACE_SYSTEM_PUMP_CALIBRATION_POLICY => 'pump_calibration',
            self::NAMESPACE_SYSTEM_SENSOR_CALIBRATION_POLICY => 'sensor_calibration',
            default => null,
        };
    }

    public function legacySystemNamespaceToAuthority(string $namespace): ?string
    {
        return match ($namespace) {
            'automation_defaults' => self::NAMESPACE_SYSTEM_AUTOMATION_DEFAULTS,
            'automation_command_templates' => self::NAMESPACE_SYSTEM_COMMAND_TEMPLATES,
            'process_calibration_defaults' => self::NAMESPACE_SYSTEM_PROCESS_CALIBRATION_DEFAULTS,
            'pid_defaults_ph' => self::NAMESPACE_SYSTEM_PID_DEFAULTS_PH,
            'pid_defaults_ec' => self::NAMESPACE_SYSTEM_PID_DEFAULTS_EC,
            'pump_calibration' => self::NAMESPACE_SYSTEM_PUMP_CALIBRATION_POLICY,
            'sensor_calibration' => self::NAMESPACE_SYSTEM_SENSOR_CALIBRATION_POLICY,
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
            'default_payload' => SystemAutomationSettingsCatalog::defaults($type === 'ph' ? 'pid_defaults_ph' : 'pid_defaults_ec'),
            'required' => false,
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
                SystemAutomationSettingsCatalog::defaults('process_calibration_defaults'),
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
            ZoneCorrectionConfigCatalog::validateFragment($phaseConfig, false);
        }
    }

    private function validatePidPayload(array $payload, string $type): void
    {
        if (array_is_list($payload)) {
            throw new InvalidArgumentException("zone.pid.{$type} must be an object.");
        }

        foreach ([
            'target',
            'dead_zone',
            'close_zone',
            'far_zone',
            'max_output',
            'min_interval_ms',
            'max_integral',
        ] as $key) {
            if (! array_key_exists($key, $payload)) {
                throw new InvalidArgumentException("zone.pid.{$type}.{$key} is required.");
            }
        }

        if (($payload['close_zone'] ?? 0) <= ($payload['dead_zone'] ?? 0)) {
            throw new InvalidArgumentException('close_zone должна быть больше dead_zone');
        }
        if (($payload['far_zone'] ?? 0) <= ($payload['close_zone'] ?? 0)) {
            throw new InvalidArgumentException('far_zone должна быть больше close_zone');
        }
        if ($type === 'ph' && (($payload['target'] ?? 0) < 4 || ($payload['target'] ?? 0) > 9)) {
            throw new InvalidArgumentException('target для pH должен быть в диапазоне 4-9');
        }
        if ($type === 'ec' && (($payload['target'] ?? 0) < 0 || ($payload['target'] ?? 0) > 10)) {
            throw new InvalidArgumentException('target для EC должен быть в диапазоне 0-10');
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
        }
    }

    private function validateGreenhouseLogicProfilePayload(array $payload): void
    {
        if (array_is_list($payload)) {
            throw new InvalidArgumentException('greenhouse.logic_profile payload must be an object.');
        }

        $activeMode = $payload['active_mode'] ?? null;
        if ($activeMode !== null && (! is_string($activeMode) || ! in_array($activeMode, ['setup', 'working'], true))) {
            throw new InvalidArgumentException('greenhouse.logic_profile.active_mode must be setup or working.');
        }

        $profiles = $payload['profiles'] ?? null;
        if (! is_array($profiles) || ($profiles !== [] && array_is_list($profiles))) {
            throw new InvalidArgumentException('greenhouse.logic_profile.profiles must be an object.');
        }

        foreach ($profiles as $mode => $profile) {
            if (! is_string($mode) || ! in_array($mode, ['setup', 'working'], true)) {
                throw new InvalidArgumentException("Unsupported greenhouse logic profile mode {$mode}.");
            }

            if (! is_array($profile) || array_is_list($profile)) {
                throw new InvalidArgumentException("greenhouse.logic_profile.profiles.{$mode} must be an object.");
            }

            $subsystems = $profile['subsystems'] ?? null;
            if (! is_array($subsystems) || array_is_list($subsystems)) {
                throw new InvalidArgumentException("greenhouse.logic_profile.profiles.{$mode}.subsystems must be an object.");
            }

            $climate = $subsystems['climate'] ?? null;
            if (! is_array($climate) || array_is_list($climate)) {
                throw new InvalidArgumentException("greenhouse.logic_profile.profiles.{$mode}.subsystems.climate must be an object.");
            }

            if (array_key_exists('targets', $climate)) {
                throw new InvalidArgumentException("greenhouse.logic_profile.profiles.{$mode}.subsystems.climate.targets is not allowed.");
            }

            if (isset($climate['execution']) && (! is_array($climate['execution']) || array_is_list($climate['execution']))) {
                throw new InvalidArgumentException("greenhouse.logic_profile.profiles.{$mode}.subsystems.climate.execution must be an object.");
            }

            foreach (array_keys($subsystems) as $subsystem) {
                if (! in_array($subsystem, ['climate'], true)) {
                    throw new InvalidArgumentException("greenhouse.logic_profile.profiles.{$mode}.subsystems.{$subsystem} is not supported.");
                }
            }
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
