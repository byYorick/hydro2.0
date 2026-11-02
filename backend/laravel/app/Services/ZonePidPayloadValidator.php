<?php

namespace App\Services;

use InvalidArgumentException;

/** Enforce schemas/zone_pid.v1.json plus its cross-field ordering constraints. */
final class ZonePidPayloadValidator
{
    public static function validate(array $payload, string $type): void
    {
        $path = "zone.pid.{$type}";
        self::requireObjectKeys($payload, ['dead_zone', 'close_zone', 'far_zone', 'zone_coeffs', 'max_integral'], $path);

        foreach (['dead_zone' => 10, 'close_zone' => 20, 'far_zone' => 50, 'max_integral' => 500] as $key => $max) {
            self::requireNumber($payload[$key], 0, $max, "{$path}.{$key}", positive: true);
        }
        if ($payload['close_zone'] <= $payload['dead_zone']) {
            throw new InvalidArgumentException('close_zone должна быть больше dead_zone');
        }
        if ($payload['far_zone'] <= $payload['close_zone']) {
            throw new InvalidArgumentException('far_zone должна быть больше close_zone');
        }

        self::requireObjectKeys($payload['zone_coeffs'], ['close', 'far'], "{$path}.zone_coeffs");
        foreach (['close', 'far'] as $zone) {
            $coeffs = $payload['zone_coeffs'][$zone];
            self::requireObjectKeys($coeffs, ['kp', 'ki', 'kd'], "{$path}.zone_coeffs.{$zone}");
            foreach (['kp' => 1000, 'ki' => 100, 'kd' => 100] as $key => $max) {
                self::requireNumber($coeffs[$key], 0, $max, "{$path}.zone_coeffs.{$zone}.{$key}");
            }
        }
    }

    private static function requireObjectKeys(mixed $value, array $keys, string $path): void
    {
        if (! is_array($value) || array_is_list($value)) {
            throw new InvalidArgumentException("{$path} must be an object.");
        }
        foreach ($keys as $key) {
            if (! array_key_exists($key, $value)) {
                throw new InvalidArgumentException("{$path}.{$key} is required.");
            }
        }
        foreach (array_keys($value) as $key) {
            if (! in_array($key, $keys, true)) {
                throw new InvalidArgumentException("{$path}.{$key} is not supported.");
            }
        }
    }

    private static function requireNumber(mixed $value, float $min, float $max, string $path, bool $positive = false): void
    {
        if ((! is_int($value) && ! is_float($value)) || ! is_finite((float) $value)
            || ($positive ? $value <= $min : $value < $min) || $value > $max) {
            $lower = $positive ? 'greater than' : 'at least';
            throw new InvalidArgumentException("{$path} must be a finite number {$lower} {$min} and at most {$max}.");
        }
    }
}
