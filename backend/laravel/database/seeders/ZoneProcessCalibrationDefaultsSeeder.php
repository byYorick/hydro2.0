<?php

namespace Database\Seeders;

use App\Models\Zone;
use App\Models\ZoneProcessCalibration;
use Illuminate\Database\Seeder;
use Illuminate\Support\Facades\Schema;

class ZoneProcessCalibrationDefaultsSeeder extends Seeder
{
    private const DEFAULTS = [
        'solution_fill' => [
            'ec_gain_per_ml' => 0.0025,
            'ph_up_gain_per_ml' => 0.0100,
            'ph_down_gain_per_ml' => 0.0100,
            'ph_per_ec_ml' => -0.0015,
            'ec_per_ph_ml' => 0.0000,
            'transport_delay_sec' => 4,
            'settle_sec' => 4,
            'confidence' => 0.90,
        ],
        'tank_recirc' => [
            'ec_gain_per_ml' => 0.0080,
            'ph_up_gain_per_ml' => 0.0180,
            'ph_down_gain_per_ml' => 0.0180,
            'ph_per_ec_ml' => -0.0025,
            'ec_per_ph_ml' => 0.0000,
            'transport_delay_sec' => 4,
            'settle_sec' => 4,
            'confidence' => 0.95,
        ],
        'irrigation' => [
            'ec_gain_per_ml' => 0.0060,
            'ph_up_gain_per_ml' => 0.0140,
            'ph_down_gain_per_ml' => 0.0140,
            'ph_per_ec_ml' => -0.0020,
            'ec_per_ph_ml' => 0.0000,
            'transport_delay_sec' => 6,
            'settle_sec' => 4,
            'confidence' => 0.85,
        ],
    ];

    public function run(): void
    {
        if (! Schema::hasTable('zones') || ! Schema::hasTable('zone_process_calibrations')) {
            $this->command?->warn('zones/zone_process_calibrations tables are missing, skipping default process calibration seed');

            return;
        }

        $now = now();
        $created = 0;

        foreach (Zone::query()->orderBy('id')->get(['id']) as $zone) {
            foreach (self::DEFAULTS as $mode => $config) {
                $hasActiveCalibration = ZoneProcessCalibration::query()
                    ->where('zone_id', $zone->id)
                    ->where('mode', $mode)
                    ->where('is_active', true)
                    ->where('valid_from', '<=', $now)
                    ->where(function ($query) use ($now): void {
                        $query->whereNull('valid_to')->orWhere('valid_to', '>', $now);
                    })
                    ->exists();

                if ($hasActiveCalibration) {
                    continue;
                }

                ZoneProcessCalibration::query()->create([
                    'zone_id' => $zone->id,
                    'mode' => $mode,
                    'ec_gain_per_ml' => $config['ec_gain_per_ml'],
                    'ph_up_gain_per_ml' => $config['ph_up_gain_per_ml'],
                    'ph_down_gain_per_ml' => $config['ph_down_gain_per_ml'],
                    'ph_per_ec_ml' => $config['ph_per_ec_ml'],
                    'ec_per_ph_ml' => $config['ec_per_ph_ml'],
                    'transport_delay_sec' => $config['transport_delay_sec'],
                    'settle_sec' => $config['settle_sec'],
                    'confidence' => $config['confidence'],
                    'source' => 'default_seed',
                    'valid_from' => $now->copy()->subMinute(),
                    'valid_to' => null,
                    'is_active' => true,
                    'meta' => [
                        'seeded_by' => static::class,
                        'observe' => [
                            'telemetry_period_sec' => 2,
                            'window_min_samples' => 3,
                            'decision_window_sec' => 6,
                            'observe_poll_sec' => 2,
                            'min_effect_fraction' => 0.25,
                            'stability_max_slope' => $mode === 'tank_recirc' ? 0.08 : 0.05,
                            'no_effect_consecutive_limit' => 3,
                        ],
                    ],
                ]);

                $created++;
            }
        }

        $this->command?->info("Default process calibrations seeded: {$created}");
    }
}
