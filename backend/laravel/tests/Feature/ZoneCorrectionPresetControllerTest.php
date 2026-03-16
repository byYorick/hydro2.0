<?php

namespace Tests\Feature;

use App\Models\User;
use App\Models\ZoneCorrectionPreset;
use Laravel\Sanctum\Sanctum;
use Tests\RefreshDatabase;
use Tests\TestCase;

class ZoneCorrectionPresetControllerTest extends TestCase
{
    use RefreshDatabase;

    protected function setUp(): void
    {
        parent::setUp();

        Sanctum::actingAs(User::factory()->create(['role' => 'admin']));
    }

    public function test_can_list_system_presets(): void
    {
        $response = $this->getJson('/api/correction-config-presets');

        $response->assertOk()
            ->assertJsonPath('data.0.scope', 'system');
    }

    public function test_system_test_node_preset_is_phase_aware(): void
    {
        $response = $this->getJson('/api/correction-config-presets');

        $response->assertOk();

        $preset = collect($response->json('data'))
            ->firstWhere('slug', 'test-node');

        $this->assertNotNull($preset);
        $this->assertSame('cross_coupled_pi_d', data_get($preset, 'config.base.controllers.ph.mode'));
        $this->assertSame(4.0, (float) data_get($preset, 'config.phases.tank_recirc.dosing.max_ec_dose_ml'));
        $this->assertSame(8.0, (float) data_get($preset, 'config.phases.solution_fill.dosing.max_ec_dose_ml'));
    }

    public function test_can_create_and_delete_custom_preset_with_phase_package(): void
    {
        $payload = [
            'name' => 'My test preset',
            'description' => 'Custom preset for test node',
            'config' => [
                'base' => [
                    'controllers' => [
                        'ph' => [
                            'mode' => 'cross_coupled_pi_d',
                            'kp' => 4.0,
                            'ki' => 0.03,
                            'kd' => 0.0,
                            'derivative_filter_alpha' => 0.35,
                            'deadband' => 0.05,
                            'max_dose_ml' => 10.0,
                            'min_interval_sec' => 60,
                            'max_integral' => 12.0,
                            'anti_windup' => ['enabled' => true],
                            'overshoot_guard' => ['enabled' => true, 'hard_min' => 4.0, 'hard_max' => 9.0],
                            'no_effect' => ['enabled' => true, 'max_count' => 2],
                            'observe' => [
                                'telemetry_period_sec' => 2,
                                'window_min_samples' => 3,
                                'decision_window_sec' => 6,
                                'observe_poll_sec' => 2,
                                'min_effect_fraction' => 0.25,
                                'stability_max_slope' => 0.02,
                                'no_effect_consecutive_limit' => 3,
                            ],
                        ],
                        'ec' => [
                            'mode' => 'supervisory_allocator',
                            'kp' => 18.0,
                            'ki' => 0.15,
                            'kd' => 0.0,
                            'derivative_filter_alpha' => 0.35,
                            'deadband' => 0.1,
                            'max_dose_ml' => 18.0,
                            'min_interval_sec' => 60,
                            'max_integral' => 30.0,
                            'anti_windup' => ['enabled' => true],
                            'overshoot_guard' => ['enabled' => true, 'hard_min' => 0.0, 'hard_max' => 4.0],
                            'no_effect' => ['enabled' => true, 'max_count' => 2],
                            'observe' => [
                                'telemetry_period_sec' => 2,
                                'window_min_samples' => 3,
                                'decision_window_sec' => 6,
                                'observe_poll_sec' => 2,
                                'min_effect_fraction' => 0.25,
                                'stability_max_slope' => 0.05,
                                'no_effect_consecutive_limit' => 3,
                            ],
                        ],
                    ],
                    'runtime' => [
                        'required_node_type' => 'irrig',
                        'clean_fill_timeout_sec' => 600,
                        'solution_fill_timeout_sec' => 900,
                        'clean_fill_retry_cycles' => 1,
                        'level_switch_on_threshold' => 0.5,
                        'clean_max_sensor_label' => 'level_clean_max',
                        'clean_min_sensor_label' => 'level_clean_min',
                        'solution_max_sensor_label' => 'level_solution_max',
                        'solution_min_sensor_label' => 'level_solution_min',
                    ],
                    'timing' => [
                        'sensor_mode_stabilization_time_sec' => 30,
                        'stabilization_sec' => 30,
                        'ec_mix_wait_sec' => 40,
                        'ph_mix_wait_sec' => 25,
                        'telemetry_max_age_sec' => 180,
                        'irr_state_max_age_sec' => 15,
                        'level_poll_interval_sec' => 30,
                    ],
                    'dosing' => [
                        'solution_volume_l' => 20.0,
                        'dose_ec_channel' => 'dose_ec_a',
                        'dose_ph_up_channel' => 'dose_ph_up',
                        'dose_ph_down_channel' => 'dose_ph_down',
                        'ec_dose_ml_per_mS_L' => 0.5,
                        'ph_dose_ml_per_unit_L' => 0.2,
                        'max_ec_dose_ml' => 16.0,
                        'max_ph_dose_ml' => 8.0,
                    ],
                    'retry' => [
                        'max_ec_correction_attempts' => 4,
                        'max_ph_correction_attempts' => 4,
                        'prepare_recirculation_timeout_sec' => 600,
                        'prepare_recirculation_max_attempts' => 3,
                        'prepare_recirculation_max_correction_attempts' => 200,
                    ],
                    'adaptive_mix_wait' => [
                        'enabled' => true,
                        'reference_volume_l' => 20.0,
                    ],
                    'tolerance' => [
                        'prepare_tolerance' => ['ph_pct' => 10.0, 'ec_pct' => 18.0],
                    ],
                    'safety' => [
                        'safe_mode_on_no_effect' => true,
                        'block_on_active_no_effect_alert' => true,
                    ],
                ],
                'phases' => [
                    'tank_recirc' => [
                        'runtime' => [
                            'required_node_type' => 'irrig',
                            'clean_fill_timeout_sec' => 600,
                            'solution_fill_timeout_sec' => 900,
                            'clean_fill_retry_cycles' => 1,
                            'level_switch_on_threshold' => 0.5,
                            'clean_max_sensor_label' => 'level_clean_max',
                            'clean_min_sensor_label' => 'level_clean_min',
                            'solution_max_sensor_label' => 'level_solution_max',
                            'solution_min_sensor_label' => 'level_solution_min',
                        ],
                        'controllers' => [
                            'ph' => [
                                'mode' => 'cross_coupled_pi_d',
                                'kp' => 3.5,
                                'ki' => 0.02,
                                'kd' => 0.0,
                                'derivative_filter_alpha' => 0.35,
                                'deadband' => 0.05,
                                'max_dose_ml' => 7.0,
                                'min_interval_sec' => 70,
                                'max_integral' => 9.0,
                                'anti_windup' => ['enabled' => true],
                                'overshoot_guard' => ['enabled' => true, 'hard_min' => 4.0, 'hard_max' => 9.0],
                                'no_effect' => ['enabled' => true, 'max_count' => 2],
                                'observe' => [
                                    'telemetry_period_sec' => 2,
                                    'window_min_samples' => 3,
                                    'decision_window_sec' => 6,
                                    'observe_poll_sec' => 2,
                                    'min_effect_fraction' => 0.25,
                                    'stability_max_slope' => 0.02,
                                    'no_effect_consecutive_limit' => 3,
                                ],
                            ],
                            'ec' => [
                                'mode' => 'supervisory_allocator',
                                'kp' => 14.0,
                                'ki' => 0.10,
                                'kd' => 0.0,
                                'derivative_filter_alpha' => 0.35,
                                'deadband' => 0.1,
                                'max_dose_ml' => 12.0,
                                'min_interval_sec' => 70,
                                'max_integral' => 22.0,
                                'anti_windup' => ['enabled' => true],
                                'overshoot_guard' => ['enabled' => true, 'hard_min' => 0.0, 'hard_max' => 4.0],
                                'no_effect' => ['enabled' => true, 'max_count' => 2],
                                'observe' => [
                                    'telemetry_period_sec' => 2,
                                    'window_min_samples' => 3,
                                    'decision_window_sec' => 6,
                                    'observe_poll_sec' => 2,
                                    'min_effect_fraction' => 0.25,
                                    'stability_max_slope' => 0.05,
                                    'no_effect_consecutive_limit' => 3,
                                ],
                            ],
                        ],
                        'timing' => [
                            'sensor_mode_stabilization_time_sec' => 30,
                            'stabilization_sec' => 30,
                            'ec_mix_wait_sec' => 55,
                            'ph_mix_wait_sec' => 35,
                            'telemetry_max_age_sec' => 180,
                            'irr_state_max_age_sec' => 15,
                            'level_poll_interval_sec' => 30,
                        ],
                        'dosing' => [
                            'solution_volume_l' => 20.0,
                            'dose_ec_channel' => 'dose_ec_a',
                            'dose_ph_up_channel' => 'dose_ph_up',
                            'dose_ph_down_channel' => 'dose_ph_down',
                            'ec_dose_ml_per_mS_L' => 0.5,
                            'ph_dose_ml_per_unit_L' => 0.2,
                            'max_ec_dose_ml' => 12.0,
                            'max_ph_dose_ml' => 6.0,
                        ],
                        'retry' => [
                            'max_ec_correction_attempts' => 4,
                            'max_ph_correction_attempts' => 4,
                            'prepare_recirculation_timeout_sec' => 480,
                            'prepare_recirculation_max_attempts' => 3,
                            'prepare_recirculation_max_correction_attempts' => 200,
                        ],
                        'tolerance' => [
                            'prepare_tolerance' => ['ph_pct' => 9.0, 'ec_pct' => 15.0],
                        ],
                        'safety' => [
                            'safe_mode_on_no_effect' => true,
                            'block_on_active_no_effect_alert' => true,
                        ],
                        'adaptive_mix_wait' => [
                            'enabled' => true,
                            'reference_volume_l' => 20.0,
                        ],
                    ],
                ],
            ],
        ];

        $create = $this->postJson('/api/correction-config-presets', $payload);

        $create->assertCreated()
            ->assertJsonPath('selected', ZoneCorrectionPreset::query()->where('name', 'My test preset')->first()->id);

        $preset = ZoneCorrectionPreset::query()->where('name', 'My test preset')->firstOrFail();
        $this->deleteJson("/api/correction-config-presets/{$preset->id}")
            ->assertOk();

        $this->assertDatabaseMissing('zone_correction_presets', [
            'id' => $preset->id,
        ]);
    }

    public function test_system_preset_cannot_be_deleted(): void
    {
        $preset = ZoneCorrectionPreset::query()->where('slug', 'safe')->firstOrFail();

        $this->deleteJson("/api/correction-config-presets/{$preset->id}")
            ->assertStatus(422);
    }
}
