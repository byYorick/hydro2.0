<?php

namespace Tests\Feature;

use App\Models\SystemAutomationSetting;
use App\Models\User;
use App\Models\Zone;
use App\Models\ZoneCorrectionPreset;
use Laravel\Sanctum\Sanctum;
use Tests\RefreshDatabase;
use Tests\TestCase;

class ZoneCorrectionConfigControllerTest extends TestCase
{
    use RefreshDatabase;

    protected function setUp(): void
    {
        parent::setUp();

        Sanctum::actingAs(User::factory()->create(['role' => 'admin']));
    }

    public function test_can_get_default_zone_correction_config(): void
    {
        $zone = Zone::factory()->create();

        $response = $this->getJson("/api/zones/{$zone->id}/correction-config");

        $response->assertOk()
            ->assertJsonPath('data.zone_id', $zone->id)
            ->assertJsonPath('data.version', 1)
            ->assertJsonPath('data.meta.phases.0', 'solution_fill')
            ->assertJsonPath('data.resolved_config.base.controllers.ph.mode', 'cross_coupled_pi_d')
            ->assertJsonPath('data.resolved_config.base.runtime.required_node_type', 'irrig')
            ->assertJsonPath('data.resolved_config.base.retry.prepare_recirculation_max_correction_attempts', 20)
            ->assertJsonFragment(['slug' => 'balanced']);
    }

    public function test_can_update_zone_correction_config_and_write_revision(): void
    {
        $zone = Zone::factory()->create();
        $preset = ZoneCorrectionPreset::query()->where('slug', 'test-node')->firstOrFail();

        $payload = [
            'preset_id' => $preset->id,
            'base_config' => [
                'controllers' => [
                    'ph' => [
                        'mode' => 'cross_coupled_pi_d',
                        'kp' => 2.8,
                        'ki' => 0.03,
                        'kd' => 0.0,
                        'deadband' => 0.05,
                        'max_dose_ml' => 9.0,
                        'min_interval_sec' => 40,
                        'max_integral' => 9.0,
                        'anti_windup' => ['enabled' => true],
                        'overshoot_guard' => ['enabled' => true, 'hard_min' => 4.0, 'hard_max' => 8.5],
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
                        'kp' => 15.0,
                        'ki' => 0.10,
                        'kd' => 0.0,
                        'deadband' => 0.08,
                        'max_dose_ml' => 14.0,
                        'min_interval_sec' => 40,
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
                    'sensor_mode_stabilization_time_sec' => 25,
                    'stabilization_sec' => 25,
                    'telemetry_max_age_sec' => 180,
                    'irr_state_max_age_sec' => 15,
                    'level_poll_interval_sec' => 30,
                ],
                'dosing' => [
                    'solution_volume_l' => 18.0,
                    'dose_ec_channel' => 'dose_ec_a',
                    'dose_ph_up_channel' => 'dose_ph_up',
                    'dose_ph_down_channel' => 'dose_ph_down',
                    'max_ec_dose_ml' => 18.0,
                    'max_ph_dose_ml' => 7.0,
                ],
                'retry' => [
                    'max_ec_correction_attempts' => 4,
                    'max_ph_correction_attempts' => 4,
                    'prepare_recirculation_timeout_sec' => 480,
                    'prepare_recirculation_max_attempts' => 3,
                    'prepare_recirculation_max_correction_attempts' => 200,
                ],
                'tolerance' => [
                    'prepare_tolerance' => ['ph_pct' => 10.0, 'ec_pct' => 16.0],
                ],
                'safety' => [
                    'safe_mode_on_no_effect' => true,
                    'block_on_active_no_effect_alert' => true,
                ],
            ],
            'phase_overrides' => [
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
                    'timing' => [
                        'sensor_mode_stabilization_time_sec' => 25,
                        'stabilization_sec' => 25,
                        'telemetry_max_age_sec' => 180,
                        'irr_state_max_age_sec' => 15,
                        'level_poll_interval_sec' => 30,
                    ],
                    'retry' => [
                        'max_ec_correction_attempts' => 4,
                        'max_ph_correction_attempts' => 4,
                        'prepare_recirculation_timeout_sec' => 540,
                        'prepare_recirculation_max_attempts' => 3,
                        'prepare_recirculation_max_correction_attempts' => 200,
                    ],
                    'dosing' => [
                        'solution_volume_l' => 18.0,
                        'dose_ec_channel' => 'dose_ec_a',
                        'dose_ph_up_channel' => 'dose_ph_up',
                        'dose_ph_down_channel' => 'dose_ph_down',
                        'max_ec_dose_ml' => 12.0,
                        'max_ph_dose_ml' => 5.0,
                    ],
                    'controllers' => [
                        'ph' => [
                            'mode' => 'cross_coupled_pi_d',
                            'kp' => 2.5,
                            'ki' => 0.02,
                            'kd' => 0.0,
                            'deadband' => 0.05,
                            'max_dose_ml' => 6.0,
                            'min_interval_sec' => 50,
                            'max_integral' => 8.0,
                            'anti_windup' => ['enabled' => true],
                            'overshoot_guard' => ['enabled' => true, 'hard_min' => 4.0, 'hard_max' => 8.5],
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
                            'kp' => 12.0,
                            'ki' => 0.08,
                            'kd' => 0.0,
                            'deadband' => 0.08,
                            'max_dose_ml' => 10.0,
                            'min_interval_sec' => 50,
                            'max_integral' => 16.0,
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
                    'tolerance' => [
                        'prepare_tolerance' => ['ph_pct' => 9.0, 'ec_pct' => 15.0],
                    ],
                    'safety' => [
                        'safe_mode_on_no_effect' => true,
                        'block_on_active_no_effect_alert' => true,
                    ],
                ],
            ],
        ];

        $response = $this->putJson("/api/zones/{$zone->id}/correction-config", $payload);

        $response->assertOk()
            ->assertJsonPath('data.preset.slug', 'test-node')
            ->assertJsonPath('data.version', 2)
            ->assertJsonPath('data.resolved_config.base.runtime.clean_fill_timeout_sec', 600)
            ->assertJsonPath('data.resolved_config.phases.tank_recirc.retry.prepare_recirculation_timeout_sec', 540)
            ->assertJsonPath('data.resolved_config.base.retry.max_ec_correction_attempts', 4);

        $this->assertDatabaseHas('zone_correction_configs', [
            'zone_id' => $zone->id,
            'preset_id' => $preset->id,
            'version' => 2,
        ]);
        $this->assertDatabaseHas('zone_correction_config_versions', [
            'zone_id' => $zone->id,
            'version' => 2,
            'change_type' => 'updated',
        ]);
        $this->assertDatabaseHas('zone_events', [
            'zone_id' => $zone->id,
            'type' => 'CORRECTION_CONFIG_UPDATED',
        ]);
    }

    public function test_rejects_invalid_phase_override(): void
    {
        $zone = Zone::factory()->create();

        $response = $this->putJson("/api/zones/{$zone->id}/correction-config", [
            'phase_overrides' => [
                'invalid_phase' => [
                    'timing' => ['telemetry_max_age_sec' => 40],
                ],
            ],
        ]);

        $response->assertStatus(422);
    }

    public function test_can_apply_preset_with_empty_override_objects(): void
    {
        $zone = Zone::factory()->create();
        $preset = ZoneCorrectionPreset::query()->where('slug', 'test-node')->firstOrFail();

        $response = $this->putJson("/api/zones/{$zone->id}/correction-config", [
            'preset_id' => $preset->id,
            'base_config' => [],
            'phase_overrides' => [],
        ]);

        $response->assertOk()
            ->assertJsonPath('data.preset.slug', 'test-node')
            ->assertJsonPath('data.version', 2)
            ->assertJsonPath('data.resolved_config.meta.preset_slug', 'test-node');
    }

    public function test_rejects_prepare_recirculation_correction_cap_above_contract_maximum(): void
    {
        $zone = Zone::factory()->create();
        $preset = ZoneCorrectionPreset::query()->where('slug', 'test-node')->firstOrFail();

        $response = $this->putJson("/api/zones/{$zone->id}/correction-config", [
            'preset_id' => $preset->id,
            'base_config' => [],
            'phase_overrides' => [
                'solution_fill' => [
                    'retry' => [
                        'prepare_recirculation_max_correction_attempts' => 501,
                    ],
                ],
            ],
        ]);

        $response->assertStatus(422)
            ->assertJsonPath('message', 'Поле retry.prepare_recirculation_max_correction_attempts должно быть <= 500.');
    }

    public function test_rejects_phase_retry_attempt_caps_above_contract_maximum(): void
    {
        $zone = Zone::factory()->create();
        $preset = ZoneCorrectionPreset::query()->where('slug', 'test-node')->firstOrFail();

        $response = $this->putJson("/api/zones/{$zone->id}/correction-config", [
            'preset_id' => $preset->id,
            'base_config' => [],
            'phase_overrides' => [
                'solution_fill' => [
                    'retry' => [
                        'max_ec_correction_attempts' => 501,
                        'max_ph_correction_attempts' => 501,
                    ],
                ],
            ],
        ]);

        $response->assertStatus(422)
            ->assertJsonPath('message', 'Поле retry.max_ec_correction_attempts должно быть <= 500.');
    }

    public function test_show_rejects_zone_pump_override_that_conflicts_with_current_system_defaults(): void
    {
        $zone = Zone::factory()->create();

        $this->putJson("/api/zones/{$zone->id}/correction-config", [
            'base_config' => [
                'pump_calibration' => [
                    'age_warning_days' => 80,
                ],
            ],
            'phase_overrides' => [],
        ])->assertOk();

        $setting = SystemAutomationSetting::query()->firstWhere('namespace', 'pump_calibration');
        $config = $setting->config;
        $config['age_critical_days'] = 60;
        $setting->update(['config' => $config]);

        $this->getJson("/api/zones/{$zone->id}/correction-config")
            ->assertStatus(422)
            ->assertJsonPath('message', 'Field pump_calibration.age_warning_days must be <= pump_calibration.age_critical_days.');
    }

    public function test_service_ignores_nonexistent_updated_by_user(): void
    {
        $zone = Zone::factory()->create();
        $preset = ZoneCorrectionPreset::query()->where('slug', 'test-node')->firstOrFail();

        $config = app(\App\Services\ZoneCorrectionConfigService::class)->upsert(
            $zone,
            [
                'preset_id' => $preset->id,
                'base_config' => [],
                'phase_overrides' => [],
            ],
            999999,
        );

        $this->assertSame($zone->id, $config->zone_id);
        $this->assertSame($preset->id, $config->preset_id);
        $this->assertNull($config->updated_by);

        $this->assertDatabaseHas('zone_correction_configs', [
            'id' => $config->id,
            'updated_by' => null,
        ]);
        $this->assertDatabaseHas('zone_correction_config_versions', [
            'zone_id' => $zone->id,
            'version' => $config->version,
            'changed_by' => null,
        ]);
    }
}
