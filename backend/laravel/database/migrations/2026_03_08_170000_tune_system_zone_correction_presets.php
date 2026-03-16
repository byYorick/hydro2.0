<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Support\Facades\DB;

return new class extends Migration
{
    public function up(): void
    {
        foreach ($this->tunedPresets() as $slug => $preset) {
            DB::table('zone_correction_presets')
                ->where('slug', $slug)
                ->update([
                    'description' => $preset['description'],
                    'config' => json_encode($preset['config'], JSON_THROW_ON_ERROR),
                    'updated_at' => now(),
                ]);
        }
    }

    public function down(): void
    {
        foreach ($this->legacyPresets() as $slug => $preset) {
            DB::table('zone_correction_presets')
                ->where('slug', $slug)
                ->update([
                    'description' => $preset['description'],
                    'config' => json_encode($preset['config'], JSON_THROW_ON_ERROR),
                    'updated_at' => now(),
                ]);
        }
    }

    private function tunedPresets(): array
    {
        return [
            'safe' => [
                'description' => 'Консервативный phase-aware preset: fill идёт мягко, recirculation ещё мягче, приоритет на минимальный риск ухода pH/EC в красную зону.',
                'config' => $this->buildPresetPackage(
                    base: [
                        'controllers' => [
                            'ph' => $this->phController(2.6, 0.015, 0.0, 0.07, 8.0, 120, 8.0, 4.2, 8.6, 2),
                            'ec' => $this->ecController(12.0, 0.08, 0.0, 0.12, 12.0, 150, 24.0, 4.0, 2),
                        ],
                        'runtime' => $this->runtimeConfig(1200, 1800, 1, 0.5),
                        'timing' => $this->timingConfig(45, 45, 300, 30, 45),
                        'dosing' => $this->dosingConfig(80.0, 12.0, 8.0),
                        'retry' => $this->retryConfig(5, 1500, 3, 20),
                        'tolerance' => $this->toleranceConfig(12.0, 20.0),
                        'safety' => $this->safetyConfig(),
                    ],
                    solutionFill: [
                        'controllers' => [
                            'ph' => ['max_dose_ml' => 10.0, 'min_interval_sec' => 75],
                            'ec' => ['max_dose_ml' => 16.0, 'min_interval_sec' => 90],
                        ],
                        'timing' => [
                        ],
                        'dosing' => [
                            'max_ec_dose_ml' => 16.0,
                            'max_ph_dose_ml' => 10.0,
                        ],
                    ],
                    tankRecirc: [
                        'controllers' => [
                            'ph' => ['deadband' => 0.06, 'max_dose_ml' => 4.0, 'min_interval_sec' => 120],
                            'ec' => ['deadband' => 0.10, 'max_dose_ml' => 8.0, 'min_interval_sec' => 180],
                        ],
                        'timing' => [
                        ],
                        'dosing' => [
                            'max_ec_dose_ml' => 8.0,
                            'max_ph_dose_ml' => 4.0,
                        ],
                        'tolerance' => $this->toleranceConfig(10.0, 16.0),
                    ],
                    irrigation: [
                        'controllers' => [
                            'ph' => ['max_dose_ml' => 3.0, 'min_interval_sec' => 150],
                            'ec' => ['max_dose_ml' => 6.0, 'min_interval_sec' => 210],
                        ],
                        'dosing' => [
                            'max_ec_dose_ml' => 6.0,
                            'max_ph_dose_ml' => 3.0,
                        ],
                    ],
                ),
            ],
            'balanced' => [
                'description' => 'Основной production preset: solution_fill работает быстрее, tank_recirc удерживает контур мягче и устойчивее.',
                'config' => $this->buildPresetPackage(
                    base: [
                        'controllers' => [
                            'ph' => $this->phController(3.8, 0.03, 0.0, 0.05, 12.0, 75, 12.0, 4.0, 8.8, 3),
                            'ec' => $this->ecController(18.0, 0.15, 0.0, 0.10, 20.0, 90, 40.0, 6.0, 3),
                        ],
                        'runtime' => $this->runtimeConfig(1200, 1800, 1, 0.5),
                        'timing' => $this->timingConfig(40, 40, 300, 30, 45),
                        'dosing' => $this->dosingConfig(100.0, 20.0, 12.0),
                        'retry' => $this->retryConfig(5, 1200, 3, 20),
                        'tolerance' => $this->toleranceConfig(15.0, 25.0),
                        'safety' => $this->safetyConfig(),
                    ],
                    solutionFill: [
                        'controllers' => [
                            'ph' => ['max_dose_ml' => 14.0, 'min_interval_sec' => 60],
                            'ec' => ['max_dose_ml' => 24.0, 'min_interval_sec' => 60],
                        ],
                        'timing' => [
                        ],
                        'dosing' => [
                            'max_ec_dose_ml' => 24.0,
                            'max_ph_dose_ml' => 14.0,
                        ],
                    ],
                    tankRecirc: [
                        'controllers' => [
                            'ph' => ['max_dose_ml' => 6.0, 'min_interval_sec' => 90],
                            'ec' => ['max_dose_ml' => 10.0, 'min_interval_sec' => 120],
                        ],
                        'timing' => [
                        ],
                        'dosing' => [
                            'max_ec_dose_ml' => 10.0,
                            'max_ph_dose_ml' => 6.0,
                        ],
                        'tolerance' => $this->toleranceConfig(12.0, 18.0),
                    ],
                    irrigation: [
                        'controllers' => [
                            'ph' => ['max_dose_ml' => 5.0, 'min_interval_sec' => 105],
                            'ec' => ['max_dose_ml' => 8.0, 'min_interval_sec' => 135],
                        ],
                        'dosing' => [
                            'max_ec_dose_ml' => 8.0,
                            'max_ph_dose_ml' => 5.0,
                        ],
                    ],
                ),
            ],
            'aggressive' => [
                'description' => 'Быстрый phase-aware preset для хорошо откалиброванных зон: fill максимально активный, recirculation остаётся ограниченным guard-ами.',
                'config' => $this->buildPresetPackage(
                    base: [
                        'controllers' => [
                            'ph' => $this->phController(7.5, 0.08, 0.02, 0.03, 18.0, 45, 24.0, 4.0, 8.8, 3),
                            'ec' => $this->ecController(32.0, 0.30, 0.0, 0.07, 36.0, 50, 80.0, 8.0, 4),
                        ],
                        'runtime' => $this->runtimeConfig(1200, 1800, 1, 0.5),
                        'timing' => $this->timingConfig(30, 30, 240, 20, 30),
                        'dosing' => $this->dosingConfig(100.0, 36.0, 18.0),
                        'retry' => $this->retryConfig(6, 900, 3, 20),
                        'tolerance' => $this->toleranceConfig(18.0, 28.0),
                        'safety' => $this->safetyConfig(),
                    ],
                    solutionFill: [
                        'controllers' => [
                            'ph' => ['max_dose_ml' => 24.0, 'min_interval_sec' => 35],
                            'ec' => ['max_dose_ml' => 42.0, 'min_interval_sec' => 35],
                        ],
                        'timing' => [
                        ],
                        'dosing' => [
                            'max_ec_dose_ml' => 42.0,
                            'max_ph_dose_ml' => 24.0,
                        ],
                    ],
                    tankRecirc: [
                        'controllers' => [
                            'ph' => ['max_dose_ml' => 10.0, 'min_interval_sec' => 70],
                            'ec' => ['max_dose_ml' => 14.0, 'min_interval_sec' => 75],
                        ],
                        'timing' => [
                        ],
                        'dosing' => [
                            'max_ec_dose_ml' => 14.0,
                            'max_ph_dose_ml' => 10.0,
                        ],
                    ],
                    irrigation: [
                        'controllers' => [
                            'ph' => ['max_dose_ml' => 8.0, 'min_interval_sec' => 90],
                            'ec' => ['max_dose_ml' => 12.0, 'min_interval_sec' => 95],
                        ],
                        'dosing' => [
                            'max_ec_dose_ml' => 12.0,
                            'max_ph_dose_ml' => 8.0,
                        ],
                    ],
                ),
            ],
            'test-node' => [
                'description' => 'Preset для test-node и HIL: компактный объём, мягкие дозы и отдельный мягкий tank_recirc profile для устойчивой сходимости на стенде.',
                'config' => $this->buildPresetPackage(
                    base: [
                        'controllers' => [
                            'ph' => $this->phController(2.4, 0.02, 0.0, 0.05, 4.0, 45, 6.0, 4.0, 8.5, 2),
                            'ec' => $this->ecController(8.0, 0.08, 0.0, 0.08, 6.0, 45, 12.0, 4.0, 2),
                        ],
                        'runtime' => $this->runtimeConfig(600, 900, 1, 0.5),
                        'timing' => $this->timingConfig(20, 20, 180, 15, 20),
                        'dosing' => $this->dosingConfig(20.0, 6.0, 4.0),
                        'retry' => $this->retryConfig(5, 600, 3, 20),
                        'tolerance' => $this->toleranceConfig(10.0, 16.0),
                        'safety' => $this->safetyConfig(),
                    ],
                    solutionFill: [
                        'controllers' => [
                            'ph' => ['max_dose_ml' => 4.0, 'min_interval_sec' => 35],
                            'ec' => ['max_dose_ml' => 8.0, 'min_interval_sec' => 35],
                        ],
                        'timing' => [
                        ],
                        'dosing' => [
                            'max_ec_dose_ml' => 8.0,
                            'max_ph_dose_ml' => 4.0,
                        ],
                    ],
                    tankRecirc: [
                        'controllers' => [
                            'ph' => ['max_dose_ml' => 3.0, 'min_interval_sec' => 75],
                            'ec' => ['max_dose_ml' => 4.0, 'min_interval_sec' => 75],
                        ],
                        'timing' => [
                        ],
                        'dosing' => [
                            'max_ec_dose_ml' => 4.0,
                            'max_ph_dose_ml' => 3.0,
                        ],
                        'retry' => $this->retryConfig(5, 600, 3, 20),
                        'tolerance' => $this->toleranceConfig(9.0, 15.0),
                    ],
                    irrigation: [
                        'controllers' => [
                            'ph' => ['max_dose_ml' => 2.5, 'min_interval_sec' => 90],
                            'ec' => ['max_dose_ml' => 3.5, 'min_interval_sec' => 90],
                        ],
                        'dosing' => [
                            'max_ec_dose_ml' => 3.5,
                            'max_ph_dose_ml' => 2.5,
                        ],
                    ],
                ),
            ],
        ];
    }

    private function legacyPresets(): array
    {
        return [
            'safe' => [
                'description' => 'Консервативный контур с мягкими дозами, длинными интервалами и минимальным риском ухода pH/EC в красную зону.',
                'config' => [
                    'controllers' => [
                        'ph' => $this->phController(3.5, 0.02, 0.0, 0.08, 12.0, 150, 12.0, 4.2, 8.8, 2),
                        'ec' => $this->ecController(18.0, 0.15, 0.0, 0.15, 30.0, 180, 60.0, 4.0, 2),
                    ],
                    'runtime' => $this->runtimeConfig(1200, 1800, 1, 0.5),
                    'timing' => $this->timingConfig(75, 75, 300, 30, 60),
                    'dosing' => $this->dosingConfig(100.0, 35.0, 15.0),
                    'retry' => $this->retryConfig(5, 1500, 3, 20),
                    'tolerance' => $this->toleranceConfig(12.0, 20.0),
                    'safety' => $this->safetyConfig(),
                ],
            ],
            'balanced' => [
                'description' => 'Сбалансированный preset для production-runtime по умолчанию.',
                'config' => [
                    'controllers' => [
                        'ph' => $this->phController(5.0, 0.05, 0.0, 0.05, 20.0, 90, 20.0, 4.0, 9.0, 3),
                        'ec' => $this->ecController(30.0, 0.30, 0.0, 0.10, 50.0, 120, 100.0, 10.0, 3),
                    ],
                    'runtime' => $this->runtimeConfig(1200, 1800, 1, 0.5),
                    'timing' => $this->timingConfig(60, 60, 300, 30, 60),
                    'dosing' => $this->dosingConfig(100.0, 50.0, 20.0),
                    'retry' => $this->retryConfig(5, 1200, 3, 20),
                    'tolerance' => $this->toleranceConfig(15.0, 25.0),
                    'safety' => $this->safetyConfig(),
                ],
            ],
            'aggressive' => [
                'description' => 'Быстрый контур для хорошо откалиброванных зон с повышенным риском overshoot.',
                'config' => [
                    'controllers' => [
                        'ph' => $this->phController(7.5, 0.08, 0.02, 0.03, 28.0, 45, 30.0, 4.0, 8.8, 3),
                        'ec' => $this->ecController(45.0, 0.50, 0.0, 0.07, 75.0, 60, 140.0, 10.0, 4),
                    ],
                    'runtime' => $this->runtimeConfig(1200, 1800, 1, 0.5),
                    'timing' => $this->timingConfig(45, 45, 240, 20, 45),
                    'dosing' => $this->dosingConfig(100.0, 80.0, 30.0),
                    'retry' => $this->retryConfig(6, 900, 3, 20),
                    'tolerance' => $this->toleranceConfig(18.0, 28.0),
                    'safety' => $this->safetyConfig(),
                ],
            ],
            'test-node' => [
                'description' => 'Preset для test-node и HIL: уменьшенные дозы, компактный объём и более частые проверки.',
                'config' => [
                    'controllers' => [
                        'ph' => $this->phController(3.0, 0.03, 0.0, 0.05, 10.0, 45, 10.0, 4.0, 8.5, 2),
                        'ec' => $this->ecController(16.0, 0.12, 0.0, 0.08, 16.0, 45, 24.0, 4.0, 2),
                    ],
                    'runtime' => $this->runtimeConfig(600, 900, 1, 0.5),
                    'timing' => $this->timingConfig(30, 30, 180, 15, 30),
                    'dosing' => $this->dosingConfig(20.0, 20.0, 8.0),
                    'retry' => $this->retryConfig(5, 600, 3, 20),
                    'tolerance' => $this->toleranceConfig(10.0, 18.0),
                    'safety' => $this->safetyConfig(),
                ],
            ],
        ];
    }

    private function buildPresetPackage(array $base, array $solutionFill, array $tankRecirc, array $irrigation): array
    {
        return [
            'base' => $base,
            'phases' => [
                'solution_fill' => $solutionFill,
                'tank_recirc' => $tankRecirc,
                'irrigation' => $irrigation,
            ],
        ];
    }

    private function phController(
        float $kp,
        float $ki,
        float $kd,
        float $deadband,
        float $maxDoseMl,
        int $minIntervalSec,
        float $maxIntegral,
        float $hardMin,
        float $hardMax,
        int $noEffectMaxCount,
    ): array {
        return [
            'mode' => 'cross_coupled_pi_d',
            'kp' => $kp,
            'ki' => $ki,
            'kd' => $kd,
            'deadband' => $deadband,
            'max_dose_ml' => $maxDoseMl,
            'min_interval_sec' => $minIntervalSec,
            'max_integral' => $maxIntegral,
            'anti_windup' => ['enabled' => true],
            'overshoot_guard' => ['enabled' => true, 'hard_min' => $hardMin, 'hard_max' => $hardMax],
            'no_effect' => ['enabled' => true, 'max_count' => $noEffectMaxCount],
        ];
    }

    private function ecController(
        float $kp,
        float $ki,
        float $kd,
        float $deadband,
        float $maxDoseMl,
        int $minIntervalSec,
        float $maxIntegral,
        float $hardMax,
        int $noEffectMaxCount,
    ): array {
        return [
            'mode' => 'supervisory_allocator',
            'kp' => $kp,
            'ki' => $ki,
            'kd' => $kd,
            'deadband' => $deadband,
            'max_dose_ml' => $maxDoseMl,
            'min_interval_sec' => $minIntervalSec,
            'max_integral' => $maxIntegral,
            'anti_windup' => ['enabled' => true],
            'overshoot_guard' => ['enabled' => true, 'hard_min' => 0.0, 'hard_max' => $hardMax],
            'no_effect' => ['enabled' => true, 'max_count' => $noEffectMaxCount],
        ];
    }

    private function runtimeConfig(
        int $cleanFillTimeoutSec,
        int $solutionFillTimeoutSec,
        int $cleanFillRetryCycles,
        float $levelSwitchOnThreshold,
    ): array {
        return [
            'required_node_type' => 'irrig',
            'clean_fill_timeout_sec' => $cleanFillTimeoutSec,
            'solution_fill_timeout_sec' => $solutionFillTimeoutSec,
            'clean_fill_retry_cycles' => $cleanFillRetryCycles,
            'level_switch_on_threshold' => $levelSwitchOnThreshold,
            'clean_max_sensor_label' => 'level_clean_max',
            'clean_min_sensor_label' => 'level_clean_min',
            'solution_max_sensor_label' => 'level_solution_max',
            'solution_min_sensor_label' => 'level_solution_min',
        ];
    }

    private function timingConfig(
        int $sensorModeStabilizationTimeSec,
        int $stabilizationSec,
        int $telemetryMaxAgeSec,
        int $irrStateMaxAgeSec,
        int $levelPollIntervalSec,
    ): array {
        return [
            'sensor_mode_stabilization_time_sec' => $sensorModeStabilizationTimeSec,
            'stabilization_sec' => $stabilizationSec,
            'telemetry_max_age_sec' => $telemetryMaxAgeSec,
            'irr_state_max_age_sec' => $irrStateMaxAgeSec,
            'level_poll_interval_sec' => $levelPollIntervalSec,
        ];
    }

    private function dosingConfig(
        float $solutionVolumeL,
        float $maxEcDoseMl,
        float $maxPhDoseMl,
    ): array {
        return [
            'solution_volume_l' => $solutionVolumeL,
            'dose_ec_channel' => 'dose_ec_a',
            'dose_ph_up_channel' => 'dose_ph_up',
            'dose_ph_down_channel' => 'dose_ph_down',
            'max_ec_dose_ml' => $maxEcDoseMl,
            'max_ph_dose_ml' => $maxPhDoseMl,
        ];
    }

    private function retryConfig(
        int $maxCorrectionAttempts,
        int $prepareRecirculationTimeoutSec,
        int $prepareRecirculationMaxAttempts,
        int $prepareRecirculationMaxCorrectionAttempts,
    ): array {
        return [
            'max_ec_correction_attempts' => $maxCorrectionAttempts,
            'max_ph_correction_attempts' => $maxCorrectionAttempts,
            'prepare_recirculation_timeout_sec' => $prepareRecirculationTimeoutSec,
            'prepare_recirculation_max_attempts' => $prepareRecirculationMaxAttempts,
            'prepare_recirculation_max_correction_attempts' => $prepareRecirculationMaxCorrectionAttempts,
        ];
    }

    private function toleranceConfig(float $phPct, float $ecPct): array
    {
        return [
            'prepare_tolerance' => [
                'ph_pct' => $phPct,
                'ec_pct' => $ecPct,
            ],
        ];
    }

    private function safetyConfig(): array
    {
        return [
            'safe_mode_on_no_effect' => true,
            'block_on_active_no_effect_alert' => true,
        ];
    }
};
