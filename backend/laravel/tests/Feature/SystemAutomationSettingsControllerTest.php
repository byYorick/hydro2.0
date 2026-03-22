<?php

namespace Tests\Feature;

use App\Models\User;
use Laravel\Sanctum\Sanctum;
use Tests\RefreshDatabase;
use Tests\TestCase;

class SystemAutomationSettingsControllerTest extends TestCase
{
    use RefreshDatabase;

    protected function setUp(): void
    {
        parent::setUp();

        Sanctum::actingAs(User::factory()->create(['role' => 'admin']));
    }

    public function test_index_returns_all_namespaces(): void
    {
        $response = $this->getJson('/api/system/automation-settings');

        $response->assertOk()
            ->assertJsonPath('data.pump_calibration.namespace', 'pump_calibration')
            ->assertJsonPath('data.sensor_calibration.namespace', 'sensor_calibration')
            ->assertJsonPath('data.process_calibration_defaults.namespace', 'process_calibration_defaults')
            ->assertJsonPath('data.automation_defaults.namespace', 'automation_defaults')
            ->assertJsonPath('data.automation_command_templates.namespace', 'automation_command_templates')
            ->assertJsonPath('data.pump_calibration.config.default_run_duration_sec', 20);
    }

    public function test_update_merges_partial_config(): void
    {
        $response = $this->putJson('/api/system/automation-settings/pump_calibration', [
            'config' => [
                'ml_per_sec_max' => 25.0,
            ],
        ]);

        $response->assertOk();
        $this->assertEquals(25.0, $response->json('data.config.ml_per_sec_max'));
        $this->assertSame(20, $response->json('data.config.default_run_duration_sec'));

        $this->assertDatabaseHas('system_automation_settings', [
            'namespace' => 'pump_calibration',
        ]);
    }

    public function test_reset_restores_catalog_defaults(): void
    {
        $this->putJson('/api/system/automation-settings/pump_calibration', [
            'config' => ['ml_per_sec_max' => 25.0],
        ])->assertOk();

        $response = $this->postJson('/api/system/automation-settings/pump_calibration/reset');

        $response->assertOk();
        $this->assertEquals(20.0, $response->json('data.config.ml_per_sec_max'));
    }

    public function test_update_rejects_inconsistent_pump_calibration_config(): void
    {
        $this->putJson('/api/system/automation-settings/pump_calibration', [
            'config' => [
                'age_warning_days' => 120,
            ],
        ])->assertStatus(422)
            ->assertJsonPath('message', 'Field pump_calibration.age_warning_days must be <= pump_calibration.age_critical_days.');
    }

    public function test_update_rejects_inconsistent_sensor_calibration_config(): void
    {
        $this->putJson('/api/system/automation-settings/sensor_calibration', [
            'config' => [
                'reminder_days' => 120,
            ],
        ])->assertStatus(422)
            ->assertJsonPath('message', 'Field sensor_calibration.reminder_days must be <= sensor_calibration.critical_days.');
    }

    public function test_update_merges_automation_defaults_config(): void
    {
        $response = $this->putJson('/api/system/automation-settings/automation_defaults', [
            'config' => [
                'water_startup_clean_fill_timeout_sec' => 1500,
                'water_refill_required_node_types_csv' => 'irrig,climate',
                'climate_enabled' => false,
            ],
        ]);

        $response->assertOk()
            ->assertJsonPath('data.config.water_startup_clean_fill_timeout_sec', 1500)
            ->assertJsonPath('data.config.water_refill_required_node_types_csv', 'irrig,climate')
            ->assertJsonPath('data.config.climate_enabled', false)
            ->assertJsonPath('data.config.water_startup_solution_fill_timeout_sec', 1800);
    }

    public function test_update_merges_process_calibration_defaults_config(): void
    {
        $response = $this->putJson('/api/system/automation-settings/process_calibration_defaults', [
            'config' => [
                'transport_delay_sec' => 24,
                'confidence' => 0.82,
            ],
        ]);

        $response->assertOk()
            ->assertJsonPath('data.config.transport_delay_sec', 24)
            ->assertJsonPath('data.config.confidence', 0.82)
            ->assertJsonPath('data.config.settle_sec', 45)
            ->assertJsonPath('data.config.ec_gain_per_ml', 0.11);
    }

    public function test_update_rejects_inconsistent_automation_defaults_config(): void
    {
        $this->putJson('/api/system/automation-settings/automation_defaults', [
            'config' => [
                'water_irrigation_recovery_target_tolerance_ec_pct' => 30,
            ],
        ])->assertStatus(422)
            ->assertJsonPath(
                'message',
                'Field automation_defaults.water_irrigation_recovery_target_tolerance_ec_pct must be <= automation_defaults.water_irrigation_recovery_degraded_tolerance_ec_pct.'
            );
    }

    public function test_update_merges_automation_command_templates_config(): void
    {
        $response = $this->putJson('/api/system/automation-settings/automation_command_templates', [
            'config' => [
                'clean_fill_start' => [
                    ['channel' => 'valve_clean_fill', 'cmd' => 'set_relay', 'params' => ['state' => true]],
                    ['channel' => 'pump_aux', 'cmd' => 'set_relay', 'params' => ['state' => true]],
                ],
            ],
        ]);

        $response->assertOk()
            ->assertJsonPath('data.config.clean_fill_start.1.channel', 'pump_aux')
            ->assertJsonPath('data.config.solution_fill_start.0.channel', 'valve_clean_supply');
    }

    public function test_non_admin_cannot_update(): void
    {
        Sanctum::actingAs(User::factory()->create(['role' => 'operator']));

        $this->putJson('/api/system/automation-settings/pump_calibration', [
            'config' => ['ml_per_sec_max' => 25.0],
        ])->assertStatus(403);
    }

    public function test_unknown_namespace_returns_404(): void
    {
        $this->getJson('/api/system/automation-settings/unknown-namespace')
            ->assertStatus(404);
    }
}
