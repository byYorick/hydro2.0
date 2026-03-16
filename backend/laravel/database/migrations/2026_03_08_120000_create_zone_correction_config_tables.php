<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    public function up(): void
    {
        Schema::create('zone_correction_presets', function (Blueprint $table): void {
            $table->id();
            $table->string('slug')->unique();
            $table->string('name');
            $table->string('scope', 16)->default('custom');
            $table->boolean('is_locked')->default(false);
            $table->boolean('is_active')->default(true);
            $table->text('description')->nullable();
            $table->jsonb('config');
            $table->foreignId('created_by')->nullable()->constrained('users')->nullOnDelete();
            $table->foreignId('updated_by')->nullable()->constrained('users')->nullOnDelete();
            $table->timestamps();
        });

        Schema::create('zone_correction_configs', function (Blueprint $table): void {
            $table->id();
            $table->foreignId('zone_id')->unique()->constrained('zones')->cascadeOnDelete();
            $table->foreignId('preset_id')->nullable()->constrained('zone_correction_presets')->nullOnDelete();
            $table->jsonb('base_config')->default(DB::raw("'{}'::jsonb"));
            $table->jsonb('phase_overrides')->default(DB::raw("'{}'::jsonb"));
            $table->jsonb('resolved_config');
            $table->unsignedInteger('version')->default(1);
            $table->foreignId('updated_by')->nullable()->constrained('users')->nullOnDelete();
            $table->timestampTz('last_applied_at')->nullable();
            $table->timestamps();
        });

        Schema::create('zone_correction_config_versions', function (Blueprint $table): void {
            $table->id();
            $table->foreignId('zone_correction_config_id')->constrained('zone_correction_configs')->cascadeOnDelete();
            $table->foreignId('zone_id')->constrained('zones')->cascadeOnDelete();
            $table->foreignId('preset_id')->nullable()->constrained('zone_correction_presets')->nullOnDelete();
            $table->unsignedInteger('version');
            $table->string('change_type', 32)->default('updated');
            $table->jsonb('base_config');
            $table->jsonb('phase_overrides');
            $table->jsonb('resolved_config');
            $table->foreignId('changed_by')->nullable()->constrained('users')->nullOnDelete();
            $table->timestampTz('changed_at');
            $table->timestamps();
        });

        $now = now();
        $systemPresets = [
            [
                'slug' => 'safe',
                'name' => 'Safe',
                'scope' => 'system',
                'is_locked' => true,
                'description' => 'Консервативный контур с мягкими дозами, длинными интервалами и минимальным риском ухода pH/EC в красную зону.',
                'config' => json_encode([
                    'controllers' => [
                        'ph' => [
                            'mode' => 'cross_coupled_pi_d',
                            'kp' => 3.5,
                            'ki' => 0.02,
                            'kd' => 0.0,
                            'derivative_filter_alpha' => 0.35,
                            'deadband' => 0.08,
                            'max_dose_ml' => 12.0,
                            'min_interval_sec' => 150,
                            'max_integral' => 12.0,
                            'anti_windup' => ['enabled' => true],
                            'overshoot_guard' => ['enabled' => true, 'hard_min' => 4.2, 'hard_max' => 8.8],
                            'no_effect' => ['enabled' => true, 'max_count' => 2],
                        ],
                        'ec' => [
                            'mode' => 'supervisory_allocator',
                            'kp' => 18.0,
                            'ki' => 0.15,
                            'kd' => 0.0,
                            'derivative_filter_alpha' => 0.35,
                            'deadband' => 0.15,
                            'max_dose_ml' => 30.0,
                            'min_interval_sec' => 180,
                            'max_integral' => 60.0,
                            'anti_windup' => ['enabled' => true],
                            'overshoot_guard' => ['enabled' => true, 'hard_min' => 0.0, 'hard_max' => 4.0],
                            'no_effect' => ['enabled' => true, 'max_count' => 2],
                        ],
                    ],
                    'timing' => [
                        'sensor_mode_stabilization_time_sec' => 75,
                        'stabilization_sec' => 75,
                        'telemetry_max_age_sec' => 300,
                        'irr_state_max_age_sec' => 30,
                        'level_poll_interval_sec' => 60,
                    ],
                    'dosing' => [
                        'solution_volume_l' => 100.0,
                        'dose_ec_channel' => 'dose_ec_a',
                        'dose_ph_up_channel' => 'dose_ph_up',
                        'dose_ph_down_channel' => 'dose_ph_down',
                        'max_ec_dose_ml' => 35.0,
                        'max_ph_dose_ml' => 15.0,
                    ],
                    'retry' => [
                        'max_ec_correction_attempts' => 5,
                        'max_ph_correction_attempts' => 5,
                        'prepare_recirculation_timeout_sec' => 1500,
                        'prepare_recirculation_max_attempts' => 3,
                        'prepare_recirculation_max_correction_attempts' => 20,
                    ],
                    'tolerance' => [
                        'prepare_tolerance' => ['ph_pct' => 12.0, 'ec_pct' => 20.0],
                    ],
                    'safety' => [
                        'safe_mode_on_no_effect' => true,
                        'block_on_active_no_effect_alert' => true,
                    ],
                ], JSON_THROW_ON_ERROR),
            ],
            [
                'slug' => 'balanced',
                'name' => 'Balanced',
                'scope' => 'system',
                'is_locked' => true,
                'description' => 'Сбалансированный preset для production-runtime по умолчанию.',
                'config' => json_encode([
                    'controllers' => [
                        'ph' => [
                            'mode' => 'cross_coupled_pi_d',
                            'kp' => 5.0,
                            'ki' => 0.05,
                            'kd' => 0.0,
                            'derivative_filter_alpha' => 0.35,
                            'deadband' => 0.05,
                            'max_dose_ml' => 20.0,
                            'min_interval_sec' => 90,
                            'max_integral' => 20.0,
                            'anti_windup' => ['enabled' => true],
                            'overshoot_guard' => ['enabled' => true, 'hard_min' => 4.0, 'hard_max' => 9.0],
                            'no_effect' => ['enabled' => true, 'max_count' => 3],
                        ],
                        'ec' => [
                            'mode' => 'supervisory_allocator',
                            'kp' => 30.0,
                            'ki' => 0.3,
                            'kd' => 0.0,
                            'derivative_filter_alpha' => 0.35,
                            'deadband' => 0.1,
                            'max_dose_ml' => 50.0,
                            'min_interval_sec' => 120,
                            'max_integral' => 100.0,
                            'anti_windup' => ['enabled' => true],
                            'overshoot_guard' => ['enabled' => true, 'hard_min' => 0.0, 'hard_max' => 10.0],
                            'no_effect' => ['enabled' => true, 'max_count' => 3],
                        ],
                    ],
                    'timing' => [
                        'sensor_mode_stabilization_time_sec' => 60,
                        'stabilization_sec' => 60,
                        'telemetry_max_age_sec' => 300,
                        'irr_state_max_age_sec' => 30,
                        'level_poll_interval_sec' => 60,
                    ],
                    'dosing' => [
                        'solution_volume_l' => 100.0,
                        'dose_ec_channel' => 'dose_ec_a',
                        'dose_ph_up_channel' => 'dose_ph_up',
                        'dose_ph_down_channel' => 'dose_ph_down',
                        'max_ec_dose_ml' => 50.0,
                        'max_ph_dose_ml' => 20.0,
                    ],
                    'retry' => [
                        'max_ec_correction_attempts' => 5,
                        'max_ph_correction_attempts' => 5,
                        'prepare_recirculation_timeout_sec' => 1200,
                        'prepare_recirculation_max_attempts' => 3,
                        'prepare_recirculation_max_correction_attempts' => 20,
                    ],
                    'tolerance' => [
                        'prepare_tolerance' => ['ph_pct' => 15.0, 'ec_pct' => 25.0],
                    ],
                    'safety' => [
                        'safe_mode_on_no_effect' => true,
                        'block_on_active_no_effect_alert' => true,
                    ],
                ], JSON_THROW_ON_ERROR),
            ],
            [
                'slug' => 'aggressive',
                'name' => 'Aggressive',
                'scope' => 'system',
                'is_locked' => true,
                'description' => 'Быстрый контур для хорошо откалиброванных зон с повышенным риском overshoot.',
                'config' => json_encode([
                    'controllers' => [
                        'ph' => [
                            'mode' => 'cross_coupled_pi_d',
                            'kp' => 7.5,
                            'ki' => 0.08,
                            'kd' => 0.02,
                            'derivative_filter_alpha' => 0.35,
                            'deadband' => 0.03,
                            'max_dose_ml' => 28.0,
                            'min_interval_sec' => 45,
                            'max_integral' => 30.0,
                            'anti_windup' => ['enabled' => true],
                            'overshoot_guard' => ['enabled' => true, 'hard_min' => 4.0, 'hard_max' => 8.8],
                            'no_effect' => ['enabled' => true, 'max_count' => 3],
                        ],
                        'ec' => [
                            'mode' => 'supervisory_allocator',
                            'kp' => 45.0,
                            'ki' => 0.5,
                            'kd' => 0.0,
                            'derivative_filter_alpha' => 0.35,
                            'deadband' => 0.07,
                            'max_dose_ml' => 75.0,
                            'min_interval_sec' => 60,
                            'max_integral' => 140.0,
                            'anti_windup' => ['enabled' => true],
                            'overshoot_guard' => ['enabled' => true, 'hard_min' => 0.0, 'hard_max' => 10.0],
                            'no_effect' => ['enabled' => true, 'max_count' => 4],
                        ],
                    ],
                    'timing' => [
                        'sensor_mode_stabilization_time_sec' => 45,
                        'stabilization_sec' => 45,
                        'telemetry_max_age_sec' => 240,
                        'irr_state_max_age_sec' => 20,
                        'level_poll_interval_sec' => 45,
                    ],
                    'dosing' => [
                        'solution_volume_l' => 100.0,
                        'dose_ec_channel' => 'dose_ec_a',
                        'dose_ph_up_channel' => 'dose_ph_up',
                        'dose_ph_down_channel' => 'dose_ph_down',
                        'max_ec_dose_ml' => 80.0,
                        'max_ph_dose_ml' => 30.0,
                    ],
                    'retry' => [
                        'max_ec_correction_attempts' => 6,
                        'max_ph_correction_attempts' => 6,
                        'prepare_recirculation_timeout_sec' => 900,
                        'prepare_recirculation_max_attempts' => 3,
                        'prepare_recirculation_max_correction_attempts' => 20,
                    ],
                    'tolerance' => [
                        'prepare_tolerance' => ['ph_pct' => 18.0, 'ec_pct' => 28.0],
                    ],
                    'safety' => [
                        'safe_mode_on_no_effect' => true,
                        'block_on_active_no_effect_alert' => true,
                    ],
                ], JSON_THROW_ON_ERROR),
            ],
            [
                'slug' => 'test-node',
                'name' => 'Test Node',
                'scope' => 'system',
                'is_locked' => true,
                'description' => 'Preset для test-node и HIL: уменьшенные дозы, компактный объём и более частые проверки.',
                'config' => json_encode([
                    'controllers' => [
                        'ph' => [
                            'mode' => 'cross_coupled_pi_d',
                            'kp' => 3.0,
                            'ki' => 0.03,
                            'kd' => 0.0,
                            'derivative_filter_alpha' => 0.35,
                            'deadband' => 0.05,
                            'max_dose_ml' => 10.0,
                            'min_interval_sec' => 45,
                            'max_integral' => 10.0,
                            'anti_windup' => ['enabled' => true],
                            'overshoot_guard' => ['enabled' => true, 'hard_min' => 4.0, 'hard_max' => 8.5],
                            'no_effect' => ['enabled' => true, 'max_count' => 2],
                        ],
                        'ec' => [
                            'mode' => 'supervisory_allocator',
                            'kp' => 16.0,
                            'ki' => 0.12,
                            'kd' => 0.0,
                            'derivative_filter_alpha' => 0.35,
                            'deadband' => 0.08,
                            'max_dose_ml' => 16.0,
                            'min_interval_sec' => 45,
                            'max_integral' => 24.0,
                            'anti_windup' => ['enabled' => true],
                            'overshoot_guard' => ['enabled' => true, 'hard_min' => 0.0, 'hard_max' => 4.0],
                            'no_effect' => ['enabled' => true, 'max_count' => 2],
                        ],
                    ],
                    'timing' => [
                        'sensor_mode_stabilization_time_sec' => 30,
                        'stabilization_sec' => 30,
                        'telemetry_max_age_sec' => 180,
                        'irr_state_max_age_sec' => 15,
                        'level_poll_interval_sec' => 30,
                    ],
                    'dosing' => [
                        'solution_volume_l' => 20.0,
                        'dose_ec_channel' => 'dose_ec_a',
                        'dose_ph_up_channel' => 'dose_ph_up',
                        'dose_ph_down_channel' => 'dose_ph_down',
                        'max_ec_dose_ml' => 20.0,
                        'max_ph_dose_ml' => 8.0,
                    ],
                    'retry' => [
                        'max_ec_correction_attempts' => 5,
                        'max_ph_correction_attempts' => 5,
                        'prepare_recirculation_timeout_sec' => 600,
                        'prepare_recirculation_max_attempts' => 3,
                        'prepare_recirculation_max_correction_attempts' => 20,
                    ],
                    'tolerance' => [
                        'prepare_tolerance' => ['ph_pct' => 10.0, 'ec_pct' => 18.0],
                    ],
                    'safety' => [
                        'safe_mode_on_no_effect' => true,
                        'block_on_active_no_effect_alert' => true,
                    ],
                ], JSON_THROW_ON_ERROR),
            ],
        ];

        DB::table('zone_correction_presets')->insert(array_map(
            static fn (array $item) => array_merge($item, [
                'is_active' => true,
                'created_at' => $now,
                'updated_at' => $now,
            ]),
            $systemPresets
        ));

        $defaultResolvedConfig = json_encode([
            'base' => json_decode($systemPresets[1]['config'], true, 512, JSON_THROW_ON_ERROR),
            'phases' => [
                'solution_fill' => json_decode($systemPresets[1]['config'], true, 512, JSON_THROW_ON_ERROR),
                'tank_recirc' => json_decode($systemPresets[1]['config'], true, 512, JSON_THROW_ON_ERROR),
                'irrigation' => json_decode($systemPresets[1]['config'], true, 512, JSON_THROW_ON_ERROR),
            ],
            'meta' => [
                'preset_slug' => null,
                'preset_name' => null,
            ],
        ], JSON_THROW_ON_ERROR);

        $zones = DB::table('zones')->select('id')->get();
        foreach ($zones as $zone) {
            $configId = DB::table('zone_correction_configs')->insertGetId([
                'zone_id' => $zone->id,
                'preset_id' => null,
                'base_config' => DB::raw("'{}'::jsonb"),
                'phase_overrides' => DB::raw("'{}'::jsonb"),
                'resolved_config' => $defaultResolvedConfig,
                'version' => 1,
                'updated_by' => null,
                'last_applied_at' => null,
                'created_at' => $now,
                'updated_at' => $now,
            ]);

            DB::table('zone_correction_config_versions')->insert([
                'zone_correction_config_id' => $configId,
                'zone_id' => $zone->id,
                'preset_id' => null,
                'version' => 1,
                'change_type' => 'bootstrap',
                'base_config' => DB::raw("'{}'::jsonb"),
                'phase_overrides' => DB::raw("'{}'::jsonb"),
                'resolved_config' => $defaultResolvedConfig,
                'changed_by' => null,
                'changed_at' => $now,
                'created_at' => $now,
                'updated_at' => $now,
            ]);
        }
    }

    public function down(): void
    {
        Schema::dropIfExists('zone_correction_config_versions');
        Schema::dropIfExists('zone_correction_configs');
        Schema::dropIfExists('zone_correction_presets');
    }
};
