<?php

namespace App\Services\Automation;

use InvalidArgumentException;

/**
 * Проверка radiation_sum_v1 без клампинга: значение вне диапазона отклоняет конфиг.
 */
class RadiationSumDecisionValidator
{
    public static function validate(array $decision, string $path): void
    {
        if (($decision['strategy'] ?? null) !== 'radiation_sum_v1') {
            return;
        }

        $config = $decision['config'] ?? null;
        if (! is_array($config) || array_is_list($config)) {
            throw new InvalidArgumentException("{$path}.config is required for radiation_sum_v1.");
        }

        foreach (['threshold_par_mol_m2', 'max_interval_sec', 'fallback_interval_sec', 'max_daily_volume_l', 'plant_count', 'irrigation_ml_per_sec'] as $key) {
            if (! array_key_exists($key, $config) || $config[$key] === null || $config[$key] === '') {
                throw new InvalidArgumentException("{$path}.config.{$key} is required.");
            }
        }

        $crop = $config['crop'] ?? 'strawberry';
        if (! in_array($crop, ['strawberry', 'lettuce'], true)) {
            throw new InvalidArgumentException("{$path}.config.crop must be strawberry or lettuce.");
        }

        $threshold = self::number($config['threshold_par_mol_m2'], "{$path}.config.threshold_par_mol_m2");
        if ($crop === 'strawberry' && ($threshold < 1.2 || $threshold > 1.5)) {
            throw new InvalidArgumentException("{$path}.config.threshold_par_mol_m2 must be in [1.2, 1.5] for strawberry.");
        }
        if ($crop === 'lettuce' && ($threshold < 0.9 || $threshold > 1.2)) {
            throw new InvalidArgumentException("{$path}.config.threshold_par_mol_m2 must be in [0.9, 1.2] for lettuce.");
        }

        $minInterval = array_key_exists('min_interval_sec', $config) && $config['min_interval_sec'] !== null
            ? self::integer($config['min_interval_sec'], "{$path}.config.min_interval_sec", 1200, 7200)
            : 1200;
        $maxInterval = self::integer($config['max_interval_sec'], "{$path}.config.max_interval_sec", 3600, 5400);
        self::integer($config['plant_count'], "{$path}.config.plant_count", 1, 20000);
        $flow = self::number($config['irrigation_ml_per_sec'], "{$path}.config.irrigation_ml_per_sec");
        if ($flow <= 0.0 || $flow > 500.0) {
            throw new InvalidArgumentException("{$path}.config.irrigation_ml_per_sec must be in (0, 500].");
        }
        if ($minInterval >= $maxInterval) {
            throw new InvalidArgumentException("{$path}.config.max_interval_sec must be greater than min_interval_sec.");
        }

        self::integer($config['fallback_interval_sec'], "{$path}.config.fallback_interval_sec", 2700, 3600);
        $liters = self::number($config['max_daily_volume_l'], "{$path}.config.max_daily_volume_l");
        if ($liters <= 0.0 || $liters > 500.0) {
            throw new InvalidArgumentException("{$path}.config.max_daily_volume_l must be in (0, 500].");
        }

        if (array_key_exists('max_daily_pulses', $config) && $config['max_daily_pulses'] !== null) {
            self::integer($config['max_daily_pulses'], "{$path}.config.max_daily_pulses", 1, 30);
        }
    }

    private static function number(mixed $value, string $path): float
    {
        if (is_bool($value) || is_string($value) || ! is_numeric($value)) {
            throw new InvalidArgumentException("{$path} must be a number.");
        }

        return (float) $value;
    }

    private static function integer(mixed $value, string $path, int $min, int $max): int
    {
        if (is_bool($value) || is_string($value) || ! is_numeric($value) || (float) $value !== (float) (int) $value) {
            throw new InvalidArgumentException("{$path} must be an integer.");
        }
        $int = (int) $value;
        if ($int < $min || $int > $max) {
            throw new InvalidArgumentException("{$path} is outside {$min}..{$max}.");
        }

        return $int;
    }
}
