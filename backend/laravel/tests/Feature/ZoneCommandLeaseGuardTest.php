<?php

namespace Tests\Feature;

use App\Models\DeviceNode;
use App\Models\User;
use App\Models\Zone;
use App\Services\PythonBridgeService;
use Illuminate\Support\Facades\DB;
use Tests\RefreshDatabase;
use Tests\TestCase;

class ZoneCommandLeaseGuardTest extends TestCase
{
    use RefreshDatabase;

    public function test_force_ph_is_rejected_when_ae3_lease_is_held(): void
    {
        $zone = Zone::factory()->create();
        $user = User::factory()->create(['role' => 'operator']);
        $user->zones()->syncWithoutDetaching([$zone->id]);

        DB::table('ae_zone_leases')->insert([
            'zone_id' => $zone->id,
            'owner' => 'ae3-worker-test',
            'leased_until' => now()->addMinutes(5),
            'updated_at' => now(),
        ]);

        $this->mock(PythonBridgeService::class, function ($mock): void {
            $mock->shouldNotReceive('sendZoneCommand');
        });

        $response = $this->actingAs($user)->postJson("/api/zones/{$zone->id}/commands", [
            'type' => 'FORCE_PH_CONTROL',
            'params' => ['target_ph' => 5.8],
        ]);

        $response->assertStatus(409)
            ->assertJsonPath('status', 'error')
            ->assertJsonPath('code', 'ae3_zone_lease_held');
    }

    public function test_force_ph_is_allowed_when_lease_expired(): void
    {
        $zone = Zone::factory()->create();
        $user = User::factory()->create(['role' => 'operator']);
        $user->zones()->syncWithoutDetaching([$zone->id]);

        DB::table('ae_zone_leases')->insert([
            'zone_id' => $zone->id,
            'owner' => 'ae3-worker-test',
            'leased_until' => now()->subMinute(),
            'updated_at' => now()->subMinute(),
        ]);

        $this->mock(PythonBridgeService::class, function ($mock): void {
            $mock->shouldReceive('sendZoneCommand')->once()->andReturn('cmd-lease-expired');
        });

        $response = $this->actingAs($user)->postJson("/api/zones/{$zone->id}/commands", [
            'type' => 'FORCE_PH_CONTROL',
            'params' => ['target_ph' => 5.8],
        ]);

        $response->assertOk()
            ->assertJsonPath('status', 'ok')
            ->assertJsonPath('data.command_id', 'cmd-lease-expired');
    }

    public function test_node_dose_is_rejected_when_ae3_lease_is_held(): void
    {
        $zone = Zone::factory()->create();
        $node = DeviceNode::factory()->create(['zone_id' => $zone->id]);
        $user = User::factory()->create(['role' => 'operator']);
        $user->zones()->syncWithoutDetaching([$zone->id]);

        DB::table('ae_zone_leases')->insert([
            'zone_id' => $zone->id,
            'owner' => 'ae3-worker-test',
            'leased_until' => now()->addMinutes(5),
            'updated_at' => now(),
        ]);

        $this->mock(PythonBridgeService::class, function ($mock): void {
            $mock->shouldNotReceive('sendNodeCommand');
        });

        $response = $this->actingAs($user)->postJson("/api/nodes/{$node->id}/commands", [
            'cmd' => 'dose',
            'channel' => 'pump_acid',
            'params' => ['duration_ms' => 1000],
        ]);

        $response->assertStatus(409)
            ->assertJsonPath('status', 'error')
            ->assertJsonPath('code', 'ae3_zone_lease_held');
    }

    public function test_node_fail_safe_off_is_allowed_when_ae3_lease_is_held(): void
    {
        $zone = Zone::factory()->create();
        $node = DeviceNode::factory()->create(['zone_id' => $zone->id]);
        $user = User::factory()->create(['role' => 'operator']);
        $user->zones()->syncWithoutDetaching([$zone->id]);

        DB::table('ae_zone_leases')->insert([
            'zone_id' => $zone->id,
            'owner' => 'ae3-worker-test',
            'leased_until' => now()->addMinutes(5),
            'updated_at' => now(),
        ]);

        $this->mock(PythonBridgeService::class, function ($mock) use ($node): void {
            $mock->shouldReceive('sendNodeCommand')
                ->once()
                ->withArgs(function ($passedNode, array $payload) use ($node): bool {
                    return $passedNode->is($node)
                        && ($payload['cmd'] ?? null) === 'set_relay'
                        && ($payload['params']['state'] ?? null) === false;
                })
                ->andReturn('cmd-fail-safe-off');
        });

        $response = $this->actingAs($user)->postJson("/api/nodes/{$node->id}/commands", [
            'cmd' => 'set_relay',
            'channel' => 'valve_irrigation',
            'params' => ['state' => false],
        ]);

        $response->assertOk()
            ->assertJsonPath('status', 'ok')
            ->assertJsonPath('data.command_id', 'cmd-fail-safe-off');
    }
}
