<?php

namespace Tests\Feature;

use App\Models\User;
use App\Models\Alert;
use App\Models\Zone;
use Tests\RefreshDatabase;
use Tests\TestCase;

class AlertsTest extends TestCase
{
    use RefreshDatabase;

    private function token(string $role = 'operator'): string
    {
        $user = User::factory()->create(['role' => $role]);
        $this->actingAs($user);

        return $user->createToken('test')->plainTextToken;
    }

    public function test_alerts_requires_auth(): void
    {
        $this->getJson('/api/alerts')->assertStatus(401);
    }

    public function test_get_alerts_list(): void
    {
        $token = $this->token();
        Alert::factory()->count(3)->create();

        $resp = $this->withHeader('Authorization', 'Bearer '.$token)
            ->getJson('/api/alerts');

        $resp->assertOk()
            ->assertJsonStructure(['status', 'data' => ['data', 'current_page']]);
    }

    public function test_get_alert_details(): void
    {
        $token = $this->token();
        $alert = Alert::factory()->create();

        $resp = $this->withHeader('Authorization', 'Bearer '.$token)
            ->getJson("/api/alerts/{$alert->id}");

        $resp->assertOk()
            ->assertJsonPath('data.id', $alert->id)
            ->assertJsonPath('data.type', $alert->type);
    }

    public function test_acknowledge_alert(): void
    {
        $token = $this->token();
        $alert = Alert::factory()->create(['status' => 'active']);

        $resp = $this->withHeader('Authorization', 'Bearer '.$token)
            ->patchJson("/api/alerts/{$alert->id}/ack");

        $resp->assertOk()
            ->assertJsonPath('data.status', 'RESOLVED');
        $this->assertDatabaseHas('alerts', [
            'id' => $alert->id,
            'status' => 'RESOLVED',
        ]);
    }

    public function test_acknowledge_already_resolved_alert_returns_error(): void
    {
        $token = $this->token();
        $alert = Alert::factory()->create(['status' => 'resolved']);

        $resp = $this->withHeader('Authorization', 'Bearer '.$token)
            ->patchJson("/api/alerts/{$alert->id}/ack");

        $resp->assertStatus(422)
            ->assertJsonPath('status', 'error')
            ->assertJsonPath('message', 'Alert is already resolved');
    }

    public function test_filter_alerts_by_zone(): void
    {
        $token = $this->token();
        $zone1 = Zone::factory()->create();
        $zone2 = Zone::factory()->create();
        Alert::factory()->create(['zone_id' => $zone1->id]);
        Alert::factory()->create(['zone_id' => $zone2->id]);

        $resp = $this->withHeader('Authorization', 'Bearer '.$token)
            ->getJson("/api/alerts?zone_id={$zone1->id}");

        $resp->assertOk();
        $data = $resp->json('data.data');
        $this->assertCount(1, $data);
        $this->assertEquals($zone1->id, $data[0]['zone_id']);
    }

    public function test_filter_alerts_by_status(): void
    {
        $token = $this->token();
        Alert::factory()->create(['status' => 'active']);
        Alert::factory()->create(['status' => 'resolved']);

        $resp = $this->withHeader('Authorization', 'Bearer '.$token)
            ->getJson('/api/alerts?status=active');

        $resp->assertOk();
        $data = $resp->json('data.data');
        $this->assertCount(1, $data);
        $this->assertEquals('active', $data[0]['status']);
    }

    public function test_filter_alerts_by_extended_fields(): void
    {
        $token = $this->token();
        $zone = Zone::factory()->create();

        Alert::factory()->create([
            'zone_id' => $zone->id,
            'source' => 'node',
            'code' => 'node_error_sensor_timeout',
            'type' => 'node_error',
            'status' => 'ACTIVE',
            'severity' => 'critical',
            'category' => 'node',
            'node_uid' => 'nd-test-1',
            'hardware_id' => 'esp32-test-1',
            'details' => ['message' => 'sensor timeout'],
        ]);

        Alert::factory()->create([
            'zone_id' => $zone->id,
            'source' => 'infra',
            'code' => 'infra_command_timeout',
            'type' => 'Command Publish Failed',
            'status' => 'ACTIVE',
            'severity' => 'error',
            'category' => 'operations',
            'node_uid' => 'nd-test-2',
            'hardware_id' => 'esp32-test-2',
            'details' => ['message' => 'command timeout'],
        ]);

        $resp = $this->withHeader('Authorization', 'Bearer '.$token)
            ->getJson('/api/alerts?source=node&severity=critical&category=node&node_uid=nd-test-1&hardware_id=esp32-test-1&q=sensor');

        $resp->assertOk();
        $data = $resp->json('data.data');
        $this->assertCount(1, $data);
        $this->assertSame('node_error_sensor_timeout', $data[0]['code']);
    }

    public function test_alert_catalog_endpoint_returns_codes(): void
    {
        $token = $this->token();

        $resp = $this->withHeader('Authorization', 'Bearer '.$token)
            ->getJson('/api/alerts/catalog');

        $resp->assertOk()
            ->assertJsonPath('status', 'ok')
            ->assertJsonStructure([
                'status',
                'data' => [
                    'meta' => ['version', 'updated_at', 'count'],
                    'items',
                ],
            ]);

        $items = $resp->json('data.items');
        $this->assertIsArray($items);
        $this->assertGreaterThan(0, count($items));
    }
}
