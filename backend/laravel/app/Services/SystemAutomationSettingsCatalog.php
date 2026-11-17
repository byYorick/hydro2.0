<?php

namespace App\Services;

use App\Support\Automation\FieldCatalogHelpBuilder;
use App\Support\Automation\ObservabilityThresholdsCatalog;
use App\Support\Automation\SystemAutomationFields;
use InvalidArgumentException;

class SystemAutomationSettingsCatalog
{
    private const FIELD_OPTIONS = SystemAutomationFields::OPTIONS;

    private const FIELD_CATALOG = SystemAutomationFields::CATALOG;

    public static function allDefaults(): array
    {
        return [
            'pump_calibration' => [
                'ml_per_sec_min' => 0.01,
                'ml_per_sec_max' => 20.0,
                'min_dose_ms' => 50,
                'max_dose_ms' => 60_000,
                'calibration_duration_min_sec' => 1,
                'calibration_duration_max_sec' => 120,
                'quality_score_basic' => 0.75,
                'quality_score_with_k' => 0.90,
                'quality_score_legacy' => 0.50,
                'age_warning_days' => 30,
                'age_critical_days' => 90,
                'default_run_duration_sec' => 20,
                'ml_per_sec_mismatch_pct' => 10.0,
                'ml_per_sec_mismatch_fail_closed' => true,
            ],
            'sensor_calibration' => [
                'ph_point_1_value' => 4.01,
                'ph_point_2_value' => 9.18,
                'ec_point_1_tds' => 1413,
                'ec_point_2_tds' => 707,
                'reminder_days' => 30,
                'critical_days' => 90,
                'command_timeout_sec' => 10,
                'ph_reference_min' => 1.0,
                'ph_reference_max' => 14.0,
                'ec_tds_reference_max' => 10000,
            ],
            'process_calibration_defaults' => [
                'ec_gain_per_ml' => 0.006,
                'ph_up_gain_per_ml' => 0.015,
                'ph_down_gain_per_ml' => 0.015,
                'ph_per_ec_ml' => -0.002,
                'ec_per_ph_ml' => 0.001,
                'transport_delay_sec' => 4,
                'settle_sec' => 12,
                'confidence' => 0.85,
            ],
            'automation_defaults' => [
                'climate_enabled' => true,
                'climate_day_temp_c' => 23.0,
                'climate_night_temp_c' => 20.0,
                'climate_day_humidity_pct' => 62.0,
                'climate_night_humidity_pct' => 70.0,
                'climate_interval_min' => 5,
                'climate_day_start_hhmm' => '07:00',
                'climate_night_start_hhmm' => '19:00',
                'climate_vent_min_pct' => 15,
                'climate_vent_max_pct' => 85,
                'climate_use_external_telemetry' => true,
                'climate_outside_temp_min_c' => 4.0,
                'climate_outside_temp_max_c' => 34.0,
                'climate_outside_humidity_max_pct' => 90,
                'climate_manual_override_enabled' => true,
                'climate_manual_override_minutes' => 30,
                'water_system_type' => 'drip',
                'water_tanks_count' => 2,
                'water_clean_tank_fill_l' => 300,
                'water_nutrient_tank_target_l' => 280,
                'water_irrigation_batch_l' => 20,
                'water_interval_min' => 30,
                'water_duration_sec' => 120,
                'water_fill_temperature_c' => 20.0,
                'water_fill_window_start_hhmm' => '05:00',
                'water_fill_window_end_hhmm' => '07:00',
                'water_target_ph' => 5.8,
                'water_target_ec' => 1.6,
                'water_ph_pct' => 5.0,
                'water_ec_pct' => 10.0,
                'water_valve_switching_enabled' => true,
                'water_correction_during_irrigation' => true,
                'water_irrigation_ec_component' => 'calcium',
                'water_drain_control_enabled' => false,
                'water_drain_target_pct' => 20,
                'water_diagnostics_enabled' => true,
                'water_diagnostics_interval_min' => 15,
                'water_cycle_start_workflow_enabled' => true,
                'water_diagnostics_workflow' => 'startup',
                'water_clean_tank_full_threshold' => 0.95,
                'water_refill_duration_sec' => 30,
                'water_refill_timeout_sec' => 600,
                'water_startup_clean_fill_timeout_sec' => 1200,
                'water_startup_solution_fill_timeout_sec' => 1800,
                'water_startup_prepare_recirculation_timeout_sec' => 900,
                'water_startup_clean_fill_retry_cycles' => 1,
                'water_startup_level_poll_interval_sec' => 60,
                'water_startup_level_switch_on_threshold' => 0.5,
                'water_startup_clean_max_sensor_label' => 'level_clean_max',
                'water_startup_solution_max_sensor_label' => 'level_solution_max',
                'water_clean_fill_min_check_delay_ms' => 5000,
                'water_solution_fill_clean_min_check_delay_ms' => 5000,
                'water_solution_fill_solution_min_check_delay_ms' => 60000,
                'water_recirculation_stop_on_solution_min' => true,
                'water_estop_debounce_ms' => 80,
                'water_irrigation_decision_strategy' => 'task',
                'water_irrigation_decision_lookback_sec' => 1800,
                'water_irrigation_decision_min_samples' => 3,
                'water_irrigation_decision_stale_after_sec' => 600,
                'water_irrigation_decision_hysteresis_pct' => 2.0,
                'water_irrigation_decision_spread_alert_threshold_pct' => 12.0,
                'water_irrigation_stop_on_solution_min' => true,
                'water_irrigation_auto_replay_after_setup' => true,
                'water_irrigation_max_setup_replays' => 1,
                'water_prepare_tolerance_ec_pct' => 10.0,
                'water_prepare_tolerance_ph_pct' => 5.0,
                'water_correction_max_ec_attempts' => 8,
                'water_correction_max_ph_attempts' => 8,
                'water_correction_prepare_recirculation_max_attempts' => 4,
                'water_correction_prepare_recirculation_max_correction_attempts' => 40,
                'water_correction_stabilization_sec' => 8,
                'water_two_tank_irrigation_start_steps' => 3,
                'water_two_tank_irrigation_stop_steps' => 3,
                'water_two_tank_clean_fill_start_steps' => 1,
                'water_two_tank_clean_fill_stop_steps' => 1,
                'water_two_tank_solution_fill_start_steps' => 3,
                'water_two_tank_solution_fill_stop_steps' => 3,
                'water_two_tank_prepare_recirculation_start_steps' => 3,
                'water_two_tank_prepare_recirculation_stop_steps' => 3,
                'water_two_tank_irrigation_recovery_start_steps' => 4,
                'water_two_tank_irrigation_recovery_stop_steps' => 4,
                'water_refill_required_node_types_csv' => 'irrig',
                'water_refill_preferred_channel' => 'fill_valve',
                'water_solution_change_enabled' => false,
                'water_solution_change_interval_min' => 180,
                'water_solution_change_duration_sec' => 120,
                'water_manual_irrigation_sec' => 90,
                'lighting_enabled' => true,
                'lighting_lux_day' => 18000,
                'lighting_lux_night' => 0,
                'lighting_hours_on' => 16.0,
                'lighting_interval_min' => 30,
                'lighting_schedule_start_hhmm' => '06:00',
                'lighting_schedule_end_hhmm' => '22:00',
                'lighting_manual_intensity_pct' => 75,
                'lighting_manual_duration_hours' => 4.0,
            ],
            'automation_command_templates' => [
                'irrigation_start' => [
                    ['channel' => 'valve_solution_supply', 'cmd' => 'set_relay', 'params' => ['state' => true]],
                    ['channel' => 'valve_irrigation', 'cmd' => 'set_relay', 'params' => ['state' => true]],
                    ['channel' => 'pump_main', 'cmd' => 'set_relay', 'params' => ['state' => true]],
                ],
                'irrigation_stop' => [
                    ['channel' => 'pump_main', 'cmd' => 'set_relay', 'params' => ['state' => false]],
                    ['channel' => 'valve_irrigation', 'cmd' => 'set_relay', 'params' => ['state' => false]],
                    ['channel' => 'valve_solution_supply', 'cmd' => 'set_relay', 'params' => ['state' => false]],
                ],
                'clean_fill_start' => [
                    ['channel' => 'valve_clean_fill', 'cmd' => 'set_relay', 'params' => ['state' => true]],
                ],
                'clean_fill_stop' => [
                    ['channel' => 'valve_clean_fill', 'cmd' => 'set_relay', 'params' => ['state' => false]],
                ],
                'solution_fill_start' => [
                    ['channel' => 'valve_clean_supply', 'cmd' => 'set_relay', 'params' => ['state' => true]],
                    ['channel' => 'valve_solution_fill', 'cmd' => 'set_relay', 'params' => ['state' => true]],
                    ['channel' => 'pump_main', 'cmd' => 'set_relay', 'params' => ['state' => true]],
                ],
                'solution_fill_stop' => [
                    ['channel' => 'pump_main', 'cmd' => 'set_relay', 'params' => ['state' => false]],
                    ['channel' => 'valve_solution_fill', 'cmd' => 'set_relay', 'params' => ['state' => false]],
                    ['channel' => 'valve_clean_supply', 'cmd' => 'set_relay', 'params' => ['state' => false]],
                ],
                'prepare_recirculation_start' => [
                    ['channel' => 'valve_solution_supply', 'cmd' => 'set_relay', 'params' => ['state' => true]],
                    ['channel' => 'valve_solution_fill', 'cmd' => 'set_relay', 'params' => ['state' => true]],
                    ['channel' => 'pump_main', 'cmd' => 'set_relay', 'params' => ['state' => true]],
                ],
                'prepare_recirculation_stop' => [
                    ['channel' => 'pump_main', 'cmd' => 'set_relay', 'params' => ['state' => false]],
                    ['channel' => 'valve_solution_fill', 'cmd' => 'set_relay', 'params' => ['state' => false]],
                    ['channel' => 'valve_solution_supply', 'cmd' => 'set_relay', 'params' => ['state' => false]],
                ],
                'irrigation_recovery_start' => [
                    ['channel' => 'valve_irrigation', 'cmd' => 'set_relay', 'params' => ['state' => false]],
                    ['channel' => 'valve_solution_supply', 'cmd' => 'set_relay', 'params' => ['state' => true]],
                    ['channel' => 'valve_solution_fill', 'cmd' => 'set_relay', 'params' => ['state' => true]],
                    ['channel' => 'pump_main', 'cmd' => 'set_relay', 'params' => ['state' => true]],
                ],
                'irrigation_recovery_stop' => [
                    ['channel' => 'pump_main', 'cmd' => 'set_relay', 'params' => ['state' => false]],
                    ['channel' => 'valve_solution_fill', 'cmd' => 'set_relay', 'params' => ['state' => false]],
                    ['channel' => 'valve_solution_supply', 'cmd' => 'set_relay', 'params' => ['state' => false]],
                    ['channel' => 'valve_irrigation', 'cmd' => 'set_relay', 'params' => ['state' => true]],
                ],
            ],
        ];
    }

    public static function namespaces(): array
    {
        return array_values(array_unique([
            ...array_keys(self::FIELD_CATALOG),
            ObservabilityThresholdsCatalog::NAMESPACE_KEY,
        ]));
    }

    public static function defaults(string $namespace): array
    {
        if ($namespace === ObservabilityThresholdsCatalog::NAMESPACE_KEY) {
            return ObservabilityThresholdsCatalog::defaults();
        }

        $defaults = self::allDefaults();
        if (! array_key_exists($namespace, $defaults)) {
            throw new InvalidArgumentException("Unknown automation settings namespace: {$namespace}");
        }

        return $defaults[$namespace];
    }

    public static function fieldCatalog(string $namespace): array
    {
        if ($namespace === ObservabilityThresholdsCatalog::NAMESPACE_KEY) {
            return ObservabilityThresholdsCatalog::fieldCatalog();
        }

        if (! array_key_exists($namespace, self::FIELD_CATALOG)) {
            throw new InvalidArgumentException("Unknown automation settings namespace: {$namespace}");
        }

        $sections = self::FIELD_CATALOG[$namespace];
        foreach ($sections as &$section) {
            foreach ($section['fields'] as &$field) {
                if (isset(self::FIELD_OPTIONS[$field['path']])) {
                    $field['option_labels'] = self::FIELD_OPTIONS[$field['path']];
                    $field['options'] = array_keys($field['option_labels']);
                }
            }
        }
        unset($section, $field);

        return FieldCatalogHelpBuilder::attachHelp($sections, $namespace);
    }

    public static function flattenFields(string $namespace): array
    {
        $fields = [];
        foreach (self::fieldCatalog($namespace) as $section) {
            foreach ($section['fields'] as $field) {
                $fields[$field['path']] = $field;
            }
        }

        return $fields;
    }

    public static function validate(string $namespace, array $config, bool $allowPartial = true): array
    {
        if ($config === []) {
            return [];
        }
        if (array_is_list($config)) {
            throw new InvalidArgumentException("Namespace {$namespace} must be an object.");
        }

        $defaults = self::defaults($namespace);
        $fields = self::flattenFields($namespace);

        foreach ($config as $key => $value) {
            if (! array_key_exists($key, $fields)) {
                throw new InvalidArgumentException("Unknown field {$namespace}.{$key}");
            }
            self::validateField($fields[$key], $value);
        }

        if (! $allowPartial) {
            foreach (array_keys($defaults) as $requiredKey) {
                if (! array_key_exists($requiredKey, $config)) {
                    throw new InvalidArgumentException("Field {$namespace}.{$requiredKey} is required.");
                }
            }
        }

        self::validateConsistency($namespace, $config, $allowPartial);

        return $config;
    }

    public static function merge(array $base, array $override): array
    {
        return ZoneCorrectionConfigCatalog::merge($base, $override);
    }

    public static function diff(array $base, array $target): array
    {
        return ZoneCorrectionConfigCatalog::diff($base, $target);
    }

    private static function validateField(array $field, mixed $value): void
    {
        $path = (string) $field['path'];
        $type = (string) $field['type'];
        if (isset($field['options']) && ! in_array($value, $field['options'], true)) {
            throw new InvalidArgumentException('Параметр «'.$field['label'].'»: выберите допустимый вариант из списка.');
        }
        if (str_ends_with($path, '_hhmm') && (! is_string($value) || ! preg_match('/^(?:[01]\d|2[0-3]):[0-5]\d$/', $value))) {
            throw new InvalidArgumentException('Параметр «'.$field['label'].'»: укажите время ЧЧ:ММ от 00:00 до 23:59.');
        }

        if ($type === 'integer') {
            if (! is_int($value)) {
                throw new InvalidArgumentException("Field {$path} must be integer.");
            }
        } elseif ($type === 'number') {
            if (! is_numeric($value)) {
                throw new InvalidArgumentException("Field {$path} must be numeric.");
            }
            $value = (float) $value;
        } elseif ($type === 'boolean') {
            if (! is_bool($value)) {
                throw new InvalidArgumentException("Field {$path} must be boolean.");
            }
        } elseif ($type === 'json') {
            if (! is_array($value)) {
                throw new InvalidArgumentException("Field {$path} must be JSON array/object.");
            }
        } elseif (! is_string($value)) {
            throw new InvalidArgumentException("Field {$path} must be string.");
        }

        if (isset($field['min']) && $value < $field['min']) {
            throw new InvalidArgumentException("Field {$path} must be >= {$field['min']}.");
        }
        if (isset($field['max']) && $value > $field['max']) {
            throw new InvalidArgumentException("Field {$path} must be <= {$field['max']}.");
        }
    }

    private static function validateConsistency(string $namespace, array $config, bool $allowPartial): void
    {
        $effectiveConfig = $allowPartial
            ? self::merge(self::defaults($namespace), $config)
            : $config;

        if ($namespace === 'pump_calibration') {
            $mlPerSecMin = (float) ($effectiveConfig['ml_per_sec_min'] ?? 0);
            $mlPerSecMax = (float) ($effectiveConfig['ml_per_sec_max'] ?? 0);
            $calibrationDurationMin = (int) ($effectiveConfig['calibration_duration_min_sec'] ?? 0);
            $calibrationDurationMax = (int) ($effectiveConfig['calibration_duration_max_sec'] ?? 0);
            $minDoseMs = (int) ($effectiveConfig['min_dose_ms'] ?? 0);
            $maxDoseMs = (int) ($effectiveConfig['max_dose_ms'] ?? 0);
            $ageWarningDays = (int) ($effectiveConfig['age_warning_days'] ?? 0);
            $ageCriticalDays = (int) ($effectiveConfig['age_critical_days'] ?? 0);

            if ($mlPerSecMin > $mlPerSecMax) {
                throw new InvalidArgumentException('Field pump_calibration.ml_per_sec_min must be <= pump_calibration.ml_per_sec_max.');
            }
            if ($calibrationDurationMin > $calibrationDurationMax) {
                throw new InvalidArgumentException('Field pump_calibration.calibration_duration_min_sec must be <= pump_calibration.calibration_duration_max_sec.');
            }
            if ($maxDoseMs > 0 && $minDoseMs > 0 && $maxDoseMs < $minDoseMs) {
                throw new InvalidArgumentException('Field pump_calibration.max_dose_ms must be >= pump_calibration.min_dose_ms.');
            }
            if ($ageWarningDays > $ageCriticalDays) {
                throw new InvalidArgumentException('Field pump_calibration.age_warning_days must be <= pump_calibration.age_critical_days.');
            }

            return;
        }

        if ($namespace === 'sensor_calibration') {
            $phReferenceMin = (float) ($effectiveConfig['ph_reference_min'] ?? 0);
            $phReferenceMax = (float) ($effectiveConfig['ph_reference_max'] ?? 0);
            $reminderDays = (int) ($effectiveConfig['reminder_days'] ?? 0);
            $criticalDays = (int) ($effectiveConfig['critical_days'] ?? 0);

            if ($phReferenceMin > $phReferenceMax) {
                throw new InvalidArgumentException('Field sensor_calibration.ph_reference_min must be <= sensor_calibration.ph_reference_max.');
            }
            if ($reminderDays > $criticalDays) {
                throw new InvalidArgumentException('Field sensor_calibration.reminder_days must be <= sensor_calibration.critical_days.');
            }

            return;
        }

        if ($namespace === 'automation_defaults') {
            $ventMin = (int) ($effectiveConfig['climate_vent_min_pct'] ?? 0);
            $ventMax = (int) ($effectiveConfig['climate_vent_max_pct'] ?? 0);
            $outsideTempMin = (float) ($effectiveConfig['climate_outside_temp_min_c'] ?? 0);
            $outsideTempMax = (float) ($effectiveConfig['climate_outside_temp_max_c'] ?? 0);
            $tanksCount = (int) ($effectiveConfig['water_tanks_count'] ?? 0);
            $systemType = (string) ($effectiveConfig['water_system_type'] ?? '');
            $workflow = (string) ($effectiveConfig['water_diagnostics_workflow'] ?? '');

            if ($ventMin > $ventMax) {
                throw new InvalidArgumentException('Field automation_defaults.climate_vent_min_pct must be <= automation_defaults.climate_vent_max_pct.');
            }
            if ($outsideTempMin > $outsideTempMax) {
                throw new InvalidArgumentException('Field automation_defaults.climate_outside_temp_min_c must be <= automation_defaults.climate_outside_temp_max_c.');
            }
            if (! in_array($systemType, ['drip', 'substrate_trays', 'nft'], true)) {
                throw new InvalidArgumentException('Field automation_defaults.water_system_type must be one of: drip, substrate_trays, nft.');
            }
            if (! in_array($tanksCount, [2, 3], true)) {
                throw new InvalidArgumentException('Field automation_defaults.water_tanks_count must be 2 or 3.');
            }
            if (! in_array($workflow, ['startup', 'cycle_start', 'diagnostics'], true)) {
                throw new InvalidArgumentException('Field automation_defaults.water_diagnostics_workflow must be one of: startup, cycle_start, diagnostics.');
            }

            return;
        }

        if ($namespace === ObservabilityThresholdsCatalog::NAMESPACE_KEY) {
            ObservabilityThresholdsCatalog::validateConsistency($effectiveConfig);

            return;
        }

        if ($namespace === 'automation_command_templates') {
            foreach ($effectiveConfig as $path => $commands) {
                self::assertRelayCommandTemplate((string) $path, $commands);
            }
        }
    }

    private static function assertRelayCommandTemplate(string $path, mixed $commands): void
    {
        if (! is_array($commands) || ! array_is_list($commands)) {
            throw new InvalidArgumentException("Field automation_command_templates.{$path} must be a JSON array of commands.");
        }

        foreach ($commands as $index => $command) {
            if (! is_array($command) || array_is_list($command)) {
                throw new InvalidArgumentException("Field automation_command_templates.{$path}[{$index}] must be an object.");
            }

            $channel = $command['channel'] ?? null;
            $cmd = $command['cmd'] ?? null;
            $params = is_array($command['params'] ?? null) ? $command['params'] : null;

            if (! is_string($channel) || trim($channel) === '') {
                throw new InvalidArgumentException("Field automation_command_templates.{$path}[{$index}].channel must be non-empty string.");
            }
            if ($cmd !== 'set_relay') {
                throw new InvalidArgumentException("Field automation_command_templates.{$path}[{$index}].cmd must be set_relay.");
            }
            if (! is_bool($params['state'] ?? null)) {
                throw new InvalidArgumentException("Field automation_command_templates.{$path}[{$index}].params.state must be boolean.");
            }
        }
    }
}
