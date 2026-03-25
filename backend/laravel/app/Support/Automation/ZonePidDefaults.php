<?php

namespace App\Support\Automation;

use InvalidArgumentException;

final class ZonePidDefaults
{
    /**
     * @return array<string, mixed>
     */
    public static function forType(string $type): array
    {
        return match ($type) {
            'ph' => [
                'dead_zone' => 0.04,
                'close_zone' => 0.18,
                'far_zone' => 0.65,
                'zone_coeffs' => [
                    'close' => [
                        'kp' => 0.18,
                        'ki' => 0.01,
                        'kd' => 0.0,
                    ],
                    'far' => [
                        'kp' => 0.28,
                        'ki' => 0.015,
                        'kd' => 0.0,
                    ],
                ],
                'max_integral' => 12.0,
            ],
            'ec' => [
                'dead_zone' => 0.06,
                'close_zone' => 0.25,
                'far_zone' => 0.9,
                'zone_coeffs' => [
                    'close' => [
                        'kp' => 0.35,
                        'ki' => 0.02,
                        'kd' => 0.0,
                    ],
                    'far' => [
                        'kp' => 0.55,
                        'ki' => 0.03,
                        'kd' => 0.0,
                    ],
                ],
                'max_integral' => 20.0,
            ],
            default => throw new InvalidArgumentException("Unsupported PID type {$type}."),
        };
    }
}
