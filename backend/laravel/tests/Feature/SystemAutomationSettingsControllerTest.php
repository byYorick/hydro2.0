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
