<?php

namespace Tests\Feature;

use App\Models\DeviceNode;
use App\Models\User;
use App\Models\Zone;
use App\Jobs\PublishNodeConfigJob;
use Illuminate\Support\Facades\Queue;
use Tests\RefreshDatabase;
use Tests\TestCase;

class NodeControllerTest extends TestCase
{
    use RefreshDatabase;

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

        $response = $this->actingAs($user)->getJson("/api/nodes/{$node->id}");

        $response->assertStatus(200);
        $data = $response->json('data');
        $this->assertArrayNotHasKey('config', $data);
    }

    public function test_nodes_search_escapes_special_characters(): void
    {
        $user = User::factory()->create();
        $zone = Zone::factory()->create();
        DeviceNode::factory()->create([
            'zone_id' => $zone->id,
            'name' => 'Test Node',
        ]);

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

        // Делаем 11 запросов (лимит 10 в минуту)
        for ($i = 0; $i < 11; $i++) {
            $response = $this->withHeader('Authorization', "Bearer {$token}")
                ->postJson('/api/nodes/register', [
                    'node_uid' => "test-node-{$i}",
                    'type' => 'ph',
                ]);
        }

        // Последний запрос должен быть заблокирован
        $response->assertStatus(429);
    }

    public function test_node_update_requires_authorization(): void
    {
        $user = User::factory()->create(['role' => 'viewer']);
        $zone = Zone::factory()->create();
        $node = DeviceNode::factory()->create(['zone_id' => $zone->id]);

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
}
