<?php

namespace Tests\Feature;

use App\Models\User;
use App\Models\DeviceNode;
use App\Models\Zone;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Tests\TestCase;

class NodesTest extends TestCase
{
    use RefreshDatabase;

    private function token(string $role = 'operator'): string
    {
        $user = User::factory()->create(['role' => $role]);
        $this->actingAs($user);

        return $user->createToken('test')->plainTextToken;
    }

    public function test_nodes_requires_auth(): void
    {
        $this->getJson('/api/nodes')->assertStatus(401);
    }

    public function test_create_node(): void
    {
        $token = $this->token();
        $resp = $this->withHeader('Authorization', 'Bearer '.$token)->postJson('/api/nodes', [
            'uid' => 'test-node-001',
            'name' => 'Test Node',
            'type' => 'ph',
            'status' => 'online',
        ]);
        $resp->assertCreated()->assertJsonPath('data.uid', 'test-node-001');
    }

    public function test_get_nodes_list(): void
    {
        $token = $this->token();
        DeviceNode::factory()->count(3)->create();

        $resp = $this->withHeader('Authorization', 'Bearer '.$token)
            ->getJson('/api/nodes');

        $resp->assertOk()
            ->assertJsonStructure(['status', 'data' => ['data', 'current_page']]);
    }

    public function test_get_node_details(): void
    {
        $token = $this->token();
        $node = DeviceNode::factory()->create();

        $resp = $this->withHeader('Authorization', 'Bearer '.$token)
            ->getJson("/api/nodes/{$node->id}");

        $resp->assertOk()
            ->assertJsonPath('data.id', $node->id)
            ->assertJsonPath('data.uid', $node->uid);
    }

    public function test_update_node(): void
    {
        $token = $this->token();
        $node = DeviceNode::factory()->create(['name' => 'Old Name']);

        $resp = $this->withHeader('Authorization', 'Bearer '.$token)
            ->patchJson("/api/nodes/{$node->id}", ['name' => 'New Name']);

        $resp->assertOk()
            ->assertJsonPath('data.name', 'New Name');
    }

    public function test_delete_node_without_dependencies(): void
    {
        $token = $this->token();
        $node = DeviceNode::factory()->create(['zone_id' => null]);

        $resp = $this->withHeader('Authorization', 'Bearer '.$token)
            ->deleteJson("/api/nodes/{$node->id}");

        $resp->assertOk();
        $this->assertDatabaseMissing('nodes', ['id' => $node->id]);
    }

    public function test_delete_node_attached_to_zone_returns_error(): void
    {
        $token = $this->token();
        $zone = Zone::factory()->create();
        $node = DeviceNode::factory()->create(['zone_id' => $zone->id]);

        $resp = $this->withHeader('Authorization', 'Bearer '.$token)
            ->deleteJson("/api/nodes/{$node->id}");

        $resp->assertStatus(422)
            ->assertJsonPath('status', 'error')
            ->assertJsonPath('message', 'Cannot delete node that is attached to a zone. Please detach from zone first.');
    }

    public function test_filter_nodes_by_zone(): void
    {
        $token = $this->token();
        $zone1 = Zone::factory()->create();
        $zone2 = Zone::factory()->create();
        DeviceNode::factory()->create(['zone_id' => $zone1->id]);
        DeviceNode::factory()->create(['zone_id' => $zone2->id]);

        $resp = $this->withHeader('Authorization', 'Bearer '.$token)
            ->getJson("/api/nodes?zone_id={$zone1->id}");

        $resp->assertOk();
        $data = $resp->json('data.data');
        $this->assertCount(1, $data);
        $this->assertEquals($zone1->id, $data[0]['zone_id']);
    }

    public function test_register_node_requires_token_when_configured(): void
    {
        // Настраиваем токен
        config(['services.python_bridge.token' => 'test-token-123']);
        
        // Без токена должен вернуть 401
        $response = $this->postJson('/api/nodes/register', [
            'node_uid' => 'test-node-001',
            'type' => 'ph',
        ]);
        
        $response->assertStatus(401)
            ->assertJsonPath('status', 'error')
            ->assertJsonPath('message', 'Unauthorized: token required');
    }

    public function test_register_node_with_valid_token(): void
    {
        config(['services.python_bridge.ingest_token' => 'test-token-123']);
        config(['services.python_bridge.token' => 'test-token-123']);
        
        $response = $this->withHeader('Authorization', 'Bearer test-token-123')
            ->postJson('/api/nodes/register', [
                'node_uid' => 'test-node-002',
                'type' => 'ph',
                'firmware_version' => '1.0.0',
            ]);
        
        $response->assertCreated()
            ->assertJsonPath('status', 'ok')
            ->assertJsonPath('data.uid', 'test-node-002');
        
        $this->assertDatabaseHas('nodes', [
            'uid' => 'test-node-002',
            'type' => 'ph',
        ]);
    }

    public function test_register_node_with_invalid_token(): void
    {
        config(['services.python_bridge.token' => 'test-token-123']);
        
        $response = $this->withHeader('Authorization', 'Bearer wrong-token')
            ->postJson('/api/nodes/register', [
                'node_uid' => 'test-node-003',
                'type' => 'ph',
            ]);
        
        $response->assertStatus(401)
            ->assertJsonPath('status', 'error')
            ->assertJsonPath('message', 'Unauthorized: invalid token');
    }

    public function test_register_node_without_token_when_not_configured(): void
    {
        // Токен не настроен - регистрация должна быть запрещена
        config(['services.python_bridge.ingest_token' => null]);
        config(['services.python_bridge.token' => null]);
        
        // Регистрация должна быть запрещена, если токен не настроен
        $response = $this->postJson('/api/nodes/register', [
            'node_uid' => 'test-node-004',
            'type' => 'ec',
        ]);
        
        // Если токен не настроен, регистрация запрещена
        $response->assertStatus(500)
            ->assertJsonPath('status', 'error')
            ->assertJsonPath('message', 'Node registration token not configured. Set PY_INGEST_TOKEN or PY_API_TOKEN.');
    }

    public function test_register_node_hello_with_token(): void
    {
        config(['services.python_bridge.ingest_token' => 'test-token-123']);
        config(['services.python_bridge.token' => 'test-token-123']);
        
        $response = $this->withHeader('Authorization', 'Bearer test-token-123')
            ->postJson('/api/nodes/register', [
                'message_type' => 'node_hello',
                'hardware_id' => 'esp32-ABCD1234',
                'node_type' => 'ph',
                'fw_version' => '2.0.1',
            ]);
        
        $response->assertCreated()
            ->assertJsonPath('status', 'ok');
        
        // Проверяем, что узел был создан
        $this->assertDatabaseHas('nodes', [
            'hardware_id' => 'esp32-ABCD1234',
            'type' => 'ph',
        ]);
    }
}

