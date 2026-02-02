<?php

namespace Tests\Feature;

use App\Models\User;
use Tests\RefreshDatabase;
use Tests\TestCase;

class CommandsTest extends TestCase
{
    use RefreshDatabase;

    public function test_zone_command_requires_auth(): void
    {
        $this->postJson('/api/zones/1/commands', [
            'type' => 'FORCE_IRRIGATION',
            'params' => ['duration_sec' => 10],
        ])->assertStatus(401);
    }

    public function test_zone_command_validation(): void
    {
        $zone = \App\Models\Zone::factory()->create();
        $node = \App\Models\DeviceNode::factory()->create(['zone_id' => $zone->id]);
        // Создаем канал напрямую, так как фабрики может не быть
        \App\Models\NodeChannel::create([
            'node_id' => $node->id,
            'channel' => 'ph_pump',
            'type' => 'pump',
        ]);
        
        $user = User::factory()->create(['role' => 'operator']);
        $this->actingAs($user);
        $token = $user->createToken('t')->plainTextToken;

        // Тест: отсутствует type
        $this->withHeader('Authorization', 'Bearer '.$token)
            ->postJson("/api/zones/{$zone->id}/commands", [])
            ->assertStatus(422);

        // Тест: отсутствует node_uid
        $this->withHeader('Authorization', 'Bearer '.$token)
            ->postJson("/api/zones/{$zone->id}/commands", [
                'type' => 'FORCE_IRRIGATION',
            ])
            ->assertStatus(422);

        // Тест: отсутствует channel
        $this->withHeader('Authorization', 'Bearer '.$token)
            ->postJson("/api/zones/{$zone->id}/commands", [
                'type' => 'FORCE_IRRIGATION',
                'node_uid' => $node->uid,
            ])
            ->assertStatus(422);
    }

    public function test_node_command_requires_state_for_set_state_and_set_relay(): void
    {
        $user = User::factory()->create(['role' => 'operator']);
        $node = \App\Models\DeviceNode::factory()->create();

        $this->actingAs($user);

        $response = $this->postJson("/api/nodes/{$node->id}/commands", [
            'cmd' => 'set_state',
            'params' => [],
        ]);

        $response
            ->assertStatus(422)
            ->assertJsonValidationErrors(['params.state']);

        $errors = $response->json('errors');
        $this->assertSame(
            'set_state/set_relay requires params.state (0/1 or true/false)',
            $errors['params.state'][0] ?? null
        );

        $response = $this->postJson("/api/nodes/{$node->id}/commands", [
            'cmd' => 'set_relay',
            'params' => [],
        ]);

        $response
            ->assertStatus(422)
            ->assertJsonValidationErrors(['params.state']);

        $errors = $response->json('errors');
        $this->assertSame(
            'set_state/set_relay requires params.state (0/1 or true/false)',
            $errors['params.state'][0] ?? null
        );
    }
}
