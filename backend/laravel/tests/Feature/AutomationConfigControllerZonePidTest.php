<?php

namespace Tests\Feature;

use App\Models\AutomationConfigDocument;
use App\Models\User;
use App\Models\Zone;
use App\Models\ZoneEvent;
use App\Services\AutomationConfigCompiler;
use App\Services\AutomationConfigRegistry;
use Tests\RefreshDatabase;
use Tests\TestCase;

class AutomationConfigControllerZonePidTest extends TestCase
{
    use RefreshDatabase;

    public function test_show_materializes_missing_zone_pid_document_with_system_defaults(): void
    {
        $admin = User::factory()->create(['role' => 'admin']);
        $zone = Zone::factory()->create();

        $response = $this->actingAs($admin)
            ->getJson("/api/automation-configs/zone/{$zone->id}/zone.pid.ph");

        $response
            ->assertOk()
            ->assertJsonPath('status', 'ok')
            ->assertJsonPath('data.namespace', AutomationConfigRegistry::NAMESPACE_ZONE_PID_PH)
            ->assertJsonPath('data.scope_type', AutomationConfigRegistry::SCOPE_ZONE)
            ->assertJsonPath('data.scope_id', $zone->id)
            ->assertJsonPath('data.payload.dead_zone', 0.04)
            ->assertJsonPath('data.payload.close_zone', 0.18)
            ->assertJsonPath('data.payload.max_integral', 12);

        $this->assertDatabaseHas('automation_config_documents', [
            'namespace' => AutomationConfigRegistry::NAMESPACE_ZONE_PID_PH,
            'scope_type' => AutomationConfigRegistry::SCOPE_ZONE,
            'scope_id' => $zone->id,
            'source' => 'bootstrap',
        ]);
    }

    public function test_show_returns_existing_bootstrap_zone_pid_document_as_valid_bootstrap_default(): void
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
            ->assertJsonPath('data.namespace', AutomationConfigRegistry::NAMESPACE_ZONE_PID_PH)
            ->assertJsonPath('data.scope_id', $zone->id)
            ->assertJsonPath('data.payload.dead_zone', 0.05)
            ->assertJsonPath('data.payload.zone_coeffs.close.kp', 5);
    }

    public function test_compiler_includes_bootstrap_zone_pid_documents_in_zone_bundle(): void
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

        $this->assertSame(0.05, data_get($bundle->config, 'zone.pid.ph.config.dead_zone'));
        $this->assertEquals(5.0, data_get($bundle->config, 'zone.pid.ph.config.zone_coeffs.close.kp'));
        $this->assertSame(0.1, data_get($bundle->config, 'zone.pid.ec.config.dead_zone'));
        $this->assertEquals(50.0, data_get($bundle->config, 'zone.pid.ec.config.zone_coeffs.far.kp'));
    }

    public function test_zone_pid_update_emits_pid_config_updated_zone_event(): void
    {
        $admin = User::factory()->create(['role' => 'admin']);
        $zone = Zone::factory()->create();

        $payload = [
            'dead_zone' => 0.05,
            'close_zone' => 0.3,
            'far_zone' => 1.0,
            'zone_coeffs' => [
                'close' => ['kp' => 5.0, 'ki' => 0.05, 'kd' => 0.0],
                'far' => ['kp' => 8.0, 'ki' => 0.02, 'kd' => 0.0],
            ],
            'max_integral' => 20.0,
        ];

        $response = $this->actingAs($admin)
            ->putJson("/api/automation-configs/zone/{$zone->id}/zone.pid.ph", [
                'payload' => $payload,
            ]);

        $response->assertOk()->assertJsonPath('status', 'ok');

        $event = ZoneEvent::query()
            ->where('zone_id', $zone->id)
            ->where('type', 'PID_CONFIG_UPDATED')
            ->first();
        $this->assertNotNull($event);
        $pj = $event->payload_json;
        $this->assertIsArray($pj);
        $this->assertSame('ph', $pj['type'] ?? null);
        $this->assertSame($admin->id, $pj['updated_by'] ?? null);
        $this->assertIsArray($pj['new_config'] ?? null);
        $this->assertEquals(5.0, data_get($pj, 'new_config.zone_coeffs.close.kp'));
    }
}
