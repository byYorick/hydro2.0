<?php

namespace App\Services;

use Illuminate\Support\Facades\DB;
use InvalidArgumentException;

/** Greenhouse climate validation shared by authority registry dispatch. */
trait ValidatesGreenhouseLogicProfile
{
    private function validateGreenhouseLogicProfilePayload(array $payload, ?int $greenhouseId = null): void
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

            $controlMode = $climate['control_mode'] ?? null;
            if ($controlMode !== null && (! is_string($controlMode) || ! in_array($controlMode, ['auto', 'semi', 'manual'], true))) {
                throw new InvalidArgumentException("greenhouse.logic_profile.profiles.{$mode}.subsystems.climate.control_mode must be auto, semi or manual.");
            }

            $climateEnabled = ($climate['enabled'] ?? false) === true;
            if ($climateEnabled && ! array_key_exists('execution', $climate)) {
                throw new InvalidArgumentException("greenhouse.logic_profile.profiles.{$mode}.subsystems.climate.execution is required when climate is enabled.");
            }

            if (isset($climate['execution']) && (! is_array($climate['execution']) || array_is_list($climate['execution']))) {
                throw new InvalidArgumentException("greenhouse.logic_profile.profiles.{$mode}.subsystems.climate.execution must be an object.");
            }

            if (isset($climate['execution']) && is_array($climate['execution'])) {
                $this->validateGreenhouseClimateExecution((string) $mode, $climate['execution'], $climateEnabled, $greenhouseId);
            }

            foreach (array_keys($subsystems) as $subsystem) {
                if (! in_array($subsystem, ['climate'], true)) {
                    throw new InvalidArgumentException("greenhouse.logic_profile.profiles.{$mode}.subsystems.{$subsystem} is not supported.");
                }
            }
        }
    }

    /**
     * @param  array<string, mixed>  $execution
     */
    private function validateGreenhouseClimateExecution(string $mode, array $execution, bool $requireTargets, ?int $greenhouseId): void
    {
        $path = "greenhouse.logic_profile.profiles.{$mode}.subsystems.climate.execution";

        $reduce = $execution['wind_reduce_threshold_ms'] ?? null;
        $close = $execution['wind_close_threshold_ms'] ?? null;
        if ($reduce !== null && $close !== null && is_numeric($reduce) && is_numeric($close)) {
            if ((float) $close < (float) $reduce) {
                throw new InvalidArgumentException(
                    "{$path}: wind_close_threshold_ms must be >= wind_reduce_threshold_ms"
                );
            }
        }

        foreach ([
            'fallback_open_pct',
            'weather_stale_max_open_pct',
            'emergency_open_pct',
            'night_base_open_pct',
            'night_min_open_pct',
            'night_max_open_pct',
            'day_base_open_pct',
            'day_min_open_pct',
            'day_max_open_pct',
            'cold_guard_max_open_pct',
            'wind_reduce_windward_max_pct',
            'wind_reduce_leeward_max_pct',
            'wind_storm_windward_max_pct',
            'wind_storm_leeward_max_pct',
            'rain_windward_position_pct',
            'rain_leeward_position_pct',
            'rain_unknown_direction_max_pct',
        ] as $pctKey) {
            $this->validateOptionalNumberRange($execution, $pctKey, 0, 100, $path);
        }

        $this->validateOptionalNumberRange($execution, 'max_step_pct', 1, 100, $path);
        $this->validateOptionalNumberRange($execution, 'position_deadband_pct', 0, 50, $path);
        if (isset($execution['max_step_pct'], $execution['position_deadband_pct'])
            && is_numeric($execution['max_step_pct'])
            && is_numeric($execution['position_deadband_pct'])
            && (float) $execution['position_deadband_pct'] > (float) $execution['max_step_pct']
        ) {
            throw new InvalidArgumentException("{$path}.position_deadband_pct must be <= max_step_pct");
        }

        foreach ([
            'decision_interval_sec' => [60, 3600],
            'min_command_interval_sec' => [0, 3600],
            'sensor_freshness_sec' => [60, 86400],
            'manual_override_max_sec' => [60, 86400],
            'daylight_lux_threshold' => [0, 200000],
        ] as $key => [$min, $max]) {
            $this->validateOptionalNumberRange($execution, $key, $min, $max, $path);
        }

        if (isset($execution['emergency_decision_interval_sec'])) {
            $maxEmergency = isset($execution['decision_interval_sec']) && is_numeric($execution['decision_interval_sec'])
                ? (float) $execution['decision_interval_sec']
                : 3600.0;
            $this->validateOptionalNumberRange($execution, 'emergency_decision_interval_sec', 10, $maxEmergency, $path);
        }

        foreach (['greenhouse_orientation_deg', 'left_roof_normal_deg', 'right_roof_normal_deg'] as $degreeKey) {
            if (array_key_exists($degreeKey, $execution) && $execution[$degreeKey] !== null) {
                $this->validateOptionalNumberRange($execution, $degreeKey, 0, 359.999, $path);
            }
        }

        if (isset($execution['day_schedule'])) {
            if (! is_array($execution['day_schedule']) || array_is_list($execution['day_schedule'])) {
                throw new InvalidArgumentException("{$path}.day_schedule must be an object.");
            }
            foreach (['start_local', 'end_local'] as $key) {
                $value = $execution['day_schedule'][$key] ?? null;
                if (! is_string($value) || ! preg_match('/^([01]\d|2[0-3]):[0-5]\d$/', $value)) {
                    throw new InvalidArgumentException("{$path}.day_schedule.{$key} must use HH:MM format.");
                }
            }
        }

        $targetPolicy = $execution['target_policy'] ?? 'greenhouse_targets';
        if (! is_string($targetPolicy) || ! in_array($targetPolicy, ['greenhouse_targets', 'primary_zone', 'active_zones_strictest'], true)) {
            throw new InvalidArgumentException("{$path}.target_policy is invalid.");
        }
        if ($targetPolicy === 'primary_zone' && (! isset($execution['primary_zone_id']) || ! is_numeric($execution['primary_zone_id']) || (int) $execution['primary_zone_id'] <= 0)) {
            throw new InvalidArgumentException("{$path}.primary_zone_id is required for primary_zone target_policy.");
        }
        if ($targetPolicy === 'primary_zone' && $greenhouseId !== null) {
            $primaryZoneId = (int) $execution['primary_zone_id'];
            $belongs = DB::table('zones')
                ->where('id', $primaryZoneId)
                ->where('greenhouse_id', $greenhouseId)
                ->exists();
            if (! $belongs) {
                throw new InvalidArgumentException("{$path}.primary_zone_id must belong to greenhouse {$greenhouseId}.");
            }
        }

        $targets = $execution['greenhouse_targets'] ?? null;
        if (! $requireTargets && $targets === null) {
            return;
        }
        if (! is_array($targets) || array_is_list($targets)) {
            throw new InvalidArgumentException("{$path}.greenhouse_targets must be an object.");
        }
        foreach (['temp_min_c', 'temp_max_c', 'humidity_min_pct', 'humidity_max_pct'] as $targetKey) {
            if (! array_key_exists($targetKey, $targets) || ! is_numeric($targets[$targetKey])) {
                throw new InvalidArgumentException("{$path}.greenhouse_targets.{$targetKey} must be numeric.");
            }
        }
        if ((float) $targets['temp_min_c'] > (float) $targets['temp_max_c']) {
            throw new InvalidArgumentException("{$path}.greenhouse_targets temp_min_c must be <= temp_max_c.");
        }
        if ((float) $targets['humidity_min_pct'] > (float) $targets['humidity_max_pct']) {
            throw new InvalidArgumentException("{$path}.greenhouse_targets humidity_min_pct must be <= humidity_max_pct.");
        }

        $this->validateGreenhouseVpdTargets($targets, $path);
    }

    /**
     * Пустая пара выключает контур. Ноль не подставляется.
     *
     * @param  array<string, mixed>  $targets
     */
    private function validateGreenhouseVpdTargets(array $targets, string $path): void
    {
        $min = $this->optionalTargetValue($targets, 'vpd_min_kpa');
        $max = $this->optionalTargetValue($targets, 'vpd_max_kpa');
        if (! $min['set'] && ! $max['set']) {
            return;
        }
        if ($min['set'] !== $max['set']) {
            throw new InvalidArgumentException(
                "{$path}.greenhouse_targets vpd_min_kpa and vpd_max_kpa must both be set or both be empty."
            );
        }

        foreach (['vpd_min_kpa' => $min['value'], 'vpd_max_kpa' => $max['value']] as $key => $value) {
            if (! is_numeric($value)) {
                throw new InvalidArgumentException("{$path}.greenhouse_targets.{$key} must be numeric.");
            }
            $number = (float) $value;
            if ($number < 0.1 || $number > 3.0) {
                throw new InvalidArgumentException("{$path}.greenhouse_targets.{$key} must be between 0.1 and 3.0.");
            }
        }

        if ((float) $min['value'] >= (float) $max['value']) {
            throw new InvalidArgumentException("{$path}.greenhouse_targets vpd_min_kpa must be < vpd_max_kpa.");
        }
    }

    /**
     * @param  array<string, mixed>  $targets
     * @return array{set: bool, value: mixed}
     */
    private function optionalTargetValue(array $targets, string $key): array
    {
        if (! array_key_exists($key, $targets) || $targets[$key] === null || $targets[$key] === '') {
            return ['set' => false, 'value' => null];
        }

        return ['set' => true, 'value' => $targets[$key]];
    }

    /**
     * @param  array<string, mixed>  $payload
     */
    private function validateOptionalNumberRange(array $payload, string $key, float $min, float $max, string $path): void
    {
        if (! array_key_exists($key, $payload) || $payload[$key] === null) {
            return;
        }

        if (! is_numeric($payload[$key])) {
            throw new InvalidArgumentException("{$path}.{$key} must be numeric.");
        }

        $value = (float) $payload[$key];
        if ($value < $min || $value > $max) {
            throw new InvalidArgumentException("{$path}.{$key} must be between {$min} and {$max}.");
        }
    }
}
