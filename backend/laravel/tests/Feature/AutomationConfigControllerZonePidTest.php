<?php

namespace Tests\Feature;

use App\Models\AutomationConfigDocument;
use App\Models\User;
use App\Models\Zone;
use App\Services\AutomationConfigCompiler;
use App\Services\AutomationConfigRegistry;
use Tests\RefreshDatabase;
use Tests\TestCase;

class AutomationConfigControllerZonePidTest extends TestCase
{
    use RefreshDatabase;

    public function test_show_does_not_materialize_missing_zone_pid_document(): void
    {
        $admin = User::factory()->create(['role' => 'admin']);
        $zone = Zone::factory()->create();

        $response = $this->actingAs($admin)
            ->getJson("/api/automation-configs/zone/{$zone->id}/zone.pid.ph");

        $response
            ->assertOk()
            ->assertJsonPath('status', 'ok')
            ->assertJsonPath('data', null);

        $this->assertDatabaseMissing('automation_config_documents', [
            'namespace' => AutomationConfigRegistry::NAMESPACE_ZONE_PID_PH,
            'scope_type' => AutomationConfigRegistry::SCOPE_ZONE,
            'scope_id' => $zone->id,
        ]);
    }

    public function test_show_treats_bootstrap_zone_pid_document_as_missing(): void
    {
        $admin = User::factory()->create(['role' => 'admin']);
        $zone = Zone::factory()->create();

        AutomationConfigDocument::query()->create([
            'namespace' => AutomationConfigRegistry::NAMESPACE_ZONE_PID_PH,
            'scope_type' => AutomationConfigRegistry::SCOPE_ZONE,
            'scope_id' => $zone->id,
            'schema_version' => 1,
            'payload' => [
                'dead_zone' => 0.05,
                'close_zone' => 0.3,
                'far_zone' => 1.0,
                'zone_coeffs' => [
                    'close' => ['kp' => 5.0, 'ki' => 0.05, 'kd' => 0.0],
                    'far' => ['kp' => 8.0, 'ki' => 0.02, 'kd' => 0.0],
                ],
                'max_integral' => 20.0,
            ],
            'status' => 'valid',
            'source' => 'bootstrap',
            'checksum' => 'bootstrap-pid-ph',
            'updated_by' => null,
        ]);

        $response = $this->actingAs($admin)
            ->getJson("/api/automation-configs/zone/{$zone->id}/zone.pid.ph");

        $response
            ->assertOk()
            ->assertJsonPath('status', 'ok')
            ->assertJsonPath('data', null);
    }

    public function test_compiler_ignores_bootstrap_zone_pid_documents_in_zone_bundle(): void
    {
        $zone = Zone::factory()->create();

        foreach ([
            AutomationConfigRegistry::NAMESPACE_ZONE_PID_PH => [
                'dead_zone' => 0.05,
                'close_zone' => 0.3,
                'far_zone' => 1.0,
                'zone_coeffs' => [
                    'close' => ['kp' => 5.0, 'ki' => 0.05, 'kd' => 0.0],
                    'far' => ['kp' => 8.0, 'ki' => 0.02, 'kd' => 0.0],
                ],
                'max_integral' => 20.0,
            ],
            AutomationConfigRegistry::NAMESPACE_ZONE_PID_EC => [
                'dead_zone' => 0.1,
                'close_zone' => 0.5,
                'far_zone' => 1.5,
                'zone_coeffs' => [
                    'close' => ['kp' => 30.0, 'ki' => 0.3, 'kd' => 0.0],
                    'far' => ['kp' => 50.0, 'ki' => 0.1, 'kd' => 0.0],
                ],
                'max_integral' => 100.0,
            ],
        ] as $namespace => $payload) {
            AutomationConfigDocument::query()->create([
                'namespace' => $namespace,
                'scope_type' => AutomationConfigRegistry::SCOPE_ZONE,
                'scope_id' => $zone->id,
                'schema_version' => 1,
                'payload' => $payload,
                'status' => 'valid',
                'source' => 'bootstrap',
                'checksum' => sha1($namespace.'|bootstrap'),
                'updated_by' => null,
            ]);
        }

        $bundle = app(AutomationConfigCompiler::class)->compileZoneBundle($zone->id);

        $this->assertSame([], data_get($bundle->config, 'zone.pid.ph.config'));
        $this->assertSame([], data_get($bundle->config, 'zone.pid.ec.config'));
    }
}
