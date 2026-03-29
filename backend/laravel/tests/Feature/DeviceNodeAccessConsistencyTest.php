<?php

namespace Tests\Feature;

use App\Models\DeviceNode;
use App\Models\User;
use App\Models\Zone;
use App\Services\PythonBridgeService;
use Illuminate\Support\Facades\DB;
use Tests\RefreshDatabase;
use Tests\TestCase;

class DeviceNodeAccessConsistencyTest extends TestCase
{
    use RefreshDatabase;

    public function test_devices_show_page_denies_access_to_inaccessible_node(): void
    {
        $user = User::factory()->create(['role' => 'viewer']);
        $zone = Zone::factory()->create();
        $node = DeviceNode::factory()->create(['zone_id' => $zone->id]);

        $response = $this->actingAs($user)->get("/devices/{$node->id}");

        $response->assertForbidden();
    }

    public function test_node_command_endpoint_denies_access_to_inaccessible_node(): void
    {
        $user = User::factory()->create(['role' => 'operator']);
        $zone = Zone::factory()->create();
        $node = DeviceNode::factory()->create(['zone_id' => $zone->id]);

        $response = $this->actingAs($user)->postJson("/api/nodes/{$node->id}/commands", [
            'cmd' => 'restart',
            'params' => [],
        ]);

        $response->assertStatus(403)
            ->assertJson([
                'status' => 'error',
                'message' => 'Forbidden: Access denied to this node',
            ]);
    }

    public function test_node_command_endpoint_allows_accessible_operator(): void
    {
        $user = User::factory()->create(['role' => 'operator']);
        $zone = Zone::factory()->create();
        $node = DeviceNode::factory()->create(['zone_id' => $zone->id]);

        DB::table('user_zones')->insert([
            'user_id' => $user->id,
            'zone_id' => $zone->id,
            'created_at' => now(),
            'updated_at' => now(),
        ]);

        $this->mock(PythonBridgeService::class, function ($mock) use ($node): void {
            $mock->shouldReceive('sendNodeCommand')
                ->once()
                ->withArgs(function ($passedNode, array $payload) use ($node): bool {
                    return $passedNode->is($node)
                        && ($payload['cmd'] ?? null) === 'restart';
                })
                ->andReturn('cmd-access-ok');
        });

        $response = $this->actingAs($user)->postJson("/api/nodes/{$node->id}/commands", [
            'cmd' => 'restart',
            'params' => [],
        ]);

        $response->assertOk()
            ->assertJsonPath('status', 'ok')
            ->assertJsonPath('data.command_id', 'cmd-access-ok');
    }

    public function test_agronomist_can_send_command_to_unassigned_node(): void
    {
        $user = User::factory()->create(['role' => 'agronomist']);
        $node = DeviceNode::factory()->create(['zone_id' => null]);

        $this->mock(PythonBridgeService::class, function ($mock) use ($node): void {
            $mock->shouldReceive('sendNodeCommand')
                ->once()
                ->withArgs(function ($passedNode, array $payload) use ($node): bool {
                    return $passedNode->is($node)
                        && ($payload['cmd'] ?? null) === 'restart';
                })
                ->andReturn('cmd-agronomist-unassigned');
        });

        $response = $this->actingAs($user)->postJson("/api/nodes/{$node->id}/commands", [
            'cmd' => 'restart',
            'params' => [],
        ]);

        $response->assertOk()
            ->assertJsonPath('status', 'ok')
            ->assertJsonPath('data.command_id', 'cmd-agronomist-unassigned');
    }
}
