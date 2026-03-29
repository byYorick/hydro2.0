<?php

namespace Tests\Feature;

use App\Models\DeviceNode;
use App\Models\ChannelBinding;
use App\Models\InfrastructureInstance;
use App\Models\NodeChannel;
use App\Models\User;
use App\Models\Greenhouse;
use App\Models\Zone;
use App\Jobs\PublishNodeConfigJob;
use Illuminate\Support\Facades\Queue;
use Illuminate\Support\Facades\DB;
use Tests\RefreshDatabase;
use Tests\TestCase;

class NodeControllerTest extends TestCase
{
    use RefreshDatabase;

    private function grantZoneAccess(User $user, Zone $zone): void
    {
        DB::table('user_zones')->insert([
            'user_id' => $user->id,
            'zone_id' => $zone->id,
            'created_at' => now(),
            'updated_at' => now(),
        ]);
    }

    public function test_nodes_index_requires_authentication(): void
    {
        $response = $this->getJson('/api/nodes');

        $response->assertStatus(401);
    }

    public function test_nodes_index_returns_nodes_for_authenticated_user(): void
    {
        $user = User::factory()->create();
        $zone = Zone::factory()->create();
        $node = DeviceNode::factory()->create(['zone_id' => $zone->id]);

        $response = $this->actingAs($user)->getJson('/api/nodes');

        $response->assertStatus(200)
            ->assertJsonStructure([
                'status',
                'data' => [
                    'data' => [
                        '*' => [
                            'id',
                            'uid',
                            'name',
                            'type',
                            'zone_id',
                            'status',
                        ],
                    ],
                ],
            ]);
    }

    public function test_nodes_index_does_not_include_config(): void
    {
        $user = User::factory()->create();
        $zone = Zone::factory()->create();
        $node = DeviceNode::factory()->create([
            'zone_id' => $zone->id,
            'config' => ['wifi' => ['ssid' => 'test', 'password' => 'secret']],
        ]);
        $this->grantZoneAccess($user, $zone);

        $response = $this->actingAs($user)->getJson('/api/nodes');

        $response->assertStatus(200);
        $data = $response->json('data.data.0');
        $this->assertArrayNotHasKey('config', $data);
    }

    public function test_nodes_show_does_not_include_config(): void
    {
        $user = User::factory()->create();
        $zone = Zone::factory()->create();
        $node = DeviceNode::factory()->create([
            'zone_id' => $zone->id,
            'config' => ['wifi' => ['ssid' => 'test', 'password' => 'secret']],
        ]);
        $this->grantZoneAccess($user, $zone);

        $response = $this->actingAs($user)->getJson("/api/nodes/{$node->id}");

        $response->assertStatus(200);
        $data = $response->json('data');
        $this->assertArrayNotHasKey('config', $data);
    }

    public function test_nodes_index_exposes_safe_pump_component_for_channel_calibration_mapping(): void
    {
        $user = User::factory()->create();
        $zone = Zone::factory()->create();
        $node = DeviceNode::factory()->create(['zone_id' => $zone->id]);
        $this->grantZoneAccess($user, $zone);

        $channel = NodeChannel::query()->create([
            'node_id' => $node->id,
            'channel' => 'pump_a',
            'type' => 'ACTUATOR',
            'metric' => 'PUMP',
            'unit' => null,
            'config' => [],
        ]);

        $instance = InfrastructureInstance::query()->create([
            'owner_type' => 'zone',
            'owner_id' => $zone->id,
            'asset_type' => 'PUMP',
            'label' => 'EC NPK Pump',
            'required' => true,
        ]);

        ChannelBinding::query()->create([
            'infrastructure_instance_id' => $instance->id,
            'node_channel_id' => $channel->id,
            'direction' => 'actuator',
            'role' => 'ec_npk_pump',
        ]);

        $response = $this->actingAs($user)->getJson("/api/nodes?zone_id={$zone->id}");

        $response->assertStatus(200)
            ->assertJsonPath('data.data.0.channels.0.pump_component', 'npk');

        $channel = $response->json('data.data.0.channels.0');
        $this->assertArrayNotHasKey('config', $channel);
    }

    public function test_nodes_index_exposes_safe_binding_role_for_channel_calibration_mapping(): void
    {
        $user = User::factory()->create();
        $zone = Zone::factory()->create();
        $node = DeviceNode::factory()->create(['zone_id' => $zone->id]);
        $this->grantZoneAccess($user, $zone);

        $channel = NodeChannel::query()->create([
            'node_id' => $node->id,
            'channel' => 'ch_relay_1',
            'type' => 'ACTUATOR',
            'metric' => 'RELAY',
            'unit' => null,
            'config' => [],
        ]);

        $instance = InfrastructureInstance::query()->create([
            'owner_type' => 'zone',
            'owner_id' => $zone->id,
            'asset_type' => 'PUMP',
            'label' => 'EC NPK Pump',
            'required' => true,
        ]);

        ChannelBinding::query()->create([
            'infrastructure_instance_id' => $instance->id,
            'node_channel_id' => $channel->id,
            'direction' => 'actuator',
            'role' => 'ec_npk_pump',
        ]);

        $response = $this->actingAs($user)->getJson("/api/nodes?zone_id={$zone->id}");

        $response->assertStatus(200)
            ->assertJsonPath('data.data.0.channels.0.binding_role', 'ec_npk_pump');

        $channelPayload = $response->json('data.data.0.channels.0');
        $this->assertArrayNotHasKey('config', $channelPayload);
    }

    public function test_nodes_search_escapes_special_characters(): void
    {
        $user = User::factory()->create();
        $zone = Zone::factory()->create();
        DeviceNode::factory()->create([
            'zone_id' => $zone->id,
            'name' => 'Test Node',
        ]);
        $this->grantZoneAccess($user, $zone);

        // Попытка SQL injection через поиск
        $response = $this->actingAs($user)->getJson('/api/nodes?search=%_');

        // Должен вернуть 200 (не ошибку SQL)
        $response->assertStatus(200);
    }

    public function test_node_registration_with_service_token(): void
    {
        $token = config('services.python_bridge.ingest_token') ?? config('services.python_bridge.token');
        
        if (!$token) {
            $this->markTestSkipped('Service token not configured');
        }

        $response = $this->withHeader('Authorization', "Bearer {$token}")
            ->postJson('/api/nodes/register', [
                'node_uid' => 'test-node-123',
                'type' => 'ph',
            ]);

        $response->assertStatus(201);
    }

    public function test_node_registration_rate_limited(): void
    {
        $token = config('services.python_bridge.ingest_token') ?? config('services.python_bridge.token');
        
        if (!$token) {
            $this->markTestSkipped('Service token not configured');
        }

        // Один и тот же узел не должен бесконечно ретраиться через общий bridge IP.
        for ($i = 0; $i < 11; $i++) {
            $response = $this->withHeader('Authorization', "Bearer {$token}")
                ->postJson('/api/nodes/register', [
                    'node_uid' => 'test-node-rate-limited',
                    'type' => 'ph',
                ]);
        }

        $response->assertStatus(429);
    }

    public function test_node_registration_allows_burst_for_distinct_nodes_behind_same_bridge_ip(): void
    {
        $token = config('services.python_bridge.ingest_token') ?? config('services.python_bridge.token');

        if (!$token) {
            $this->markTestSkipped('Service token not configured');
        }

        for ($i = 0; $i < 11; $i++) {
            $response = $this->withHeader('Authorization', "Bearer {$token}")
                ->postJson('/api/nodes/register', [
                    'node_uid' => "test-node-burst-{$i}",
                    'type' => 'ph',
                ]);

            $response->assertStatus(201);
        }
    }

    public function test_node_update_requires_authorization(): void
    {
        $user = User::factory()->create(['role' => 'viewer']);
        $zone = Zone::factory()->create();
        $node = DeviceNode::factory()->create(['zone_id' => $zone->id]);
        $this->grantZoneAccess($user, $zone);

        $response = $this->actingAs($user)->putJson("/api/nodes/{$node->id}", [
            'name' => 'Updated Name',
        ]);

        // Viewer не может обновлять ноды
        $response->assertStatus(403);
    }

    public function test_node_update_allows_operator(): void
    {
        $user = User::factory()->create(['role' => 'operator']);
        $zone = Zone::factory()->create();
        $node = DeviceNode::factory()->create(['zone_id' => $zone->id]);
        $this->grantZoneAccess($user, $zone);

        $response = $this->actingAs($user)->putJson("/api/nodes/{$node->id}", [
            'name' => 'Updated Name',
        ]);

        $response->assertStatus(200);
        $this->assertEquals('Updated Name', $node->fresh()->name);
    }

    public function test_publish_config_dispatches_job(): void
    {
        Queue::fake();

        $user = User::factory()->create(['role' => 'operator']);
        $zone = Zone::factory()->create();
        $node = DeviceNode::factory()->create(['zone_id' => $zone->id]);
        $this->grantZoneAccess($user, $zone);

        $response = $this->actingAs($user)->postJson("/api/nodes/{$node->id}/config/publish", [
            'config' => [
                'channels' => [],
            ],
        ]);

        $response->assertStatus(200)
            ->assertJsonPath('status', 'ok');

        Queue::assertPushed(PublishNodeConfigJob::class, function (PublishNodeConfigJob $job) use ($node) {
            return $job->nodeId === $node->id;
        });
    }

    public function test_agronomist_can_list_unassigned_nodes(): void
    {
        $user = User::factory()->create(['role' => 'agronomist']);
        $node = DeviceNode::factory()->create(['zone_id' => null, 'status' => 'online']);

        $response = $this->actingAs($user)->getJson('/api/nodes?unassigned=true');

        $response->assertOk()
            ->assertJsonPath('data.data.0.id', $node->id)
            ->assertJsonPath('data.data.0.uid', $node->uid);
    }

    public function test_agronomist_can_filter_greenhouse_nodes_with_unassigned_without_explicit_greenhouse_acl(): void
    {
        $user = User::factory()->create(['role' => 'agronomist']);
        $greenhouse = Greenhouse::factory()->create();
        $zone = Zone::factory()->create(['greenhouse_id' => $greenhouse->id]);
        $this->grantZoneAccess($user, $zone);

        $assignedNode = DeviceNode::factory()->create([
            'zone_id' => $zone->id,
            'status' => 'online',
        ]);
        $unassignedNode = DeviceNode::factory()->create([
            'zone_id' => null,
            'status' => 'online',
        ]);

        $response = $this->actingAs($user)
            ->getJson("/api/nodes?greenhouse_id={$greenhouse->id}&include_unassigned=true");

        $ids = array_column($response->json('data.data') ?? [], 'id');

        $response->assertOk();
        $this->assertContains($assignedNode->id, $ids);
        $this->assertContains($unassignedNode->id, $ids);
    }
}
