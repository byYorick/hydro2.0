<?php

namespace App\Support\Automation;

use InvalidArgumentException;

final class ZoneProcessCalibrationDefaults
{
    /**
     * @return array<string, float|int>
     */
    public static function forMode(string $mode): array
    {
        $common = [
            'ph_per_ec_ml' => -0.002,
            'ec_per_ph_ml' => 0.001,
            'transport_delay_sec' => 4,
            'settle_sec' => 12,
            'confidence' => 0.85,
        ];

        return match ($mode) {
            'generic' => $common + [
                'ec_gain_per_ml' => 0.006,
                'ph_up_gain_per_ml' => 0.015,
                'ph_down_gain_per_ml' => 0.015,
            ],
            'solution_fill' => $common + [
                'ec_gain_per_ml' => 0.0016,
                'ph_up_gain_per_ml' => 0.004,
                'ph_down_gain_per_ml' => 0.004,
            ],
            'tank_recirc' => $common + [
                'ec_gain_per_ml' => 0.010,
                'ph_up_gain_per_ml' => 0.022,
                'ph_down_gain_per_ml' => 0.022,
            ],
            'irrigation' => $common + [
                'ec_gain_per_ml' => 0.008,
                'ph_up_gain_per_ml' => 0.018,
                'ph_down_gain_per_ml' => 0.018,
            ],
            default => throw new InvalidArgumentException("Unsupported process calibration mode {$mode}."),
        };
    }
}
