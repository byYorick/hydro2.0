<?php

namespace Tests\Feature;

use App\Models\User;
use App\Models\Alert;
use App\Models\Zone;
use Illuminate\Foundation\Testing\RefreshDatabase;
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
}

