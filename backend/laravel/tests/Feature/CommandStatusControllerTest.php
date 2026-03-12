<?php

namespace Tests\Feature;

use App\Models\User;
use App\Models\Zone;
use App\Models\DeviceNode;
use App\Models\Command;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Tests\TestCase;

class CommandStatusControllerTest extends TestCase
{
    use RefreshDatabase;

    public function test_command_status_requires_auth(): void
    {
        // Роут защищен middleware 'auth', который возвращает стандартное сообщение Laravel
        $response = $this->getJson('/api/commands/test-cmd-id/status');
        
        $response->assertStatus(401)
            ->assertJsonStructure([
                'status',
                'code',
                'message',
            ]);
    }

    public function test_command_status_returns_404_for_nonexistent_command(): void
    {
        $user = User::factory()->create(['role' => 'viewer']);
        $this->actingAs($user);
        $token = $user->createToken('test')->plainTextToken;

        $response = $this->withHeader('Authorization', 'Bearer ' . $token)
            ->getJson('/api/commands/nonexistent-cmd-id/status');
        
        $response->assertStatus(404)
            ->assertJson([
                'status' => 'error',
                'code' => 'NOT_FOUND',
                'message' => 'Command not found',
            ]);
    }

    public function test_command_status_allows_access_for_admin(): void
    {
        $user = User::factory()->create(['role' => 'admin']);
        $this->actingAs($user);
        $token = $user->createToken('test')->plainTextToken;

        $zone = Zone::factory()->create();
        $command = Command::create([
            'cmd_id' => 'test-cmd-1',
            'zone_id' => $zone->id,
            'cmd' => 'FORCE_IRRIGATION',
            'status' => 'pending',
        ]);

        $response = $this->withHeader('Authorization', 'Bearer ' . $token)
            ->getJson("/api/commands/{$command->cmd_id}/status");
        
        $response->assertOk()
            ->assertJson([
                'status' => 'ok',
                'data' => [
                    'cmd_id' => $command->cmd_id,
                    'status' => 'pending',
                ],
            ]);
    }

    public function test_command_status_allows_access_for_viewer_with_zone_access(): void
    {
        $user = User::factory()->create(['role' => 'viewer']);
        $this->actingAs($user);
        $token = $user->createToken('test')->plainTextToken;

        $zone = Zone::factory()->create();
        $command = Command::create([
            'cmd_id' => 'test-cmd-2',
            'zone_id' => $zone->id,
            'cmd' => 'FORCE_IRRIGATION',
            'status' => 'completed',
        ]);

        $response = $this->withHeader('Authorization', 'Bearer ' . $token)
            ->getJson("/api/commands/{$command->cmd_id}/status");
        
        $response->assertOk()
            ->assertJson([
                'status' => 'ok',
                'data' => [
                    'cmd_id' => $command->cmd_id,
                    'status' => 'completed',
                ],
            ]);
    }

    public function test_command_status_allows_access_via_node(): void
    {
        $user = User::factory()->create(['role' => 'operator']);
        $this->actingAs($user);
        $token = $user->createToken('test')->plainTextToken;

        $zone = Zone::factory()->create();
        $node = DeviceNode::factory()->create(['zone_id' => $zone->id]);
        $command = Command::create([
            'cmd_id' => 'test-cmd-3',
            'node_id' => $node->id,
            'cmd' => 'FORCE_PH_CONTROL',
            'status' => 'pending',
        ]);

        $response = $this->withHeader('Authorization', 'Bearer ' . $token)
            ->getJson("/api/commands/{$command->cmd_id}/status");
        
        $response->assertOk()
            ->assertJson([
                'status' => 'ok',
                'data' => [
                    'cmd_id' => $command->cmd_id,
                    'status' => 'pending',
                ],
            ]);
    }

    public function test_command_status_denies_access_for_command_without_zone_or_node(): void
    {
        $user = User::factory()->create(['role' => 'viewer']);
        $this->actingAs($user);
        $token = $user->createToken('test')->plainTextToken;

        // Команда без zone_id и node_id - доступна только админам
        $command = Command::create([
            'cmd_id' => 'test-cmd-4',
            'cmd' => 'SYSTEM_COMMAND',
            'status' => 'pending',
        ]);

        $response = $this->withHeader('Authorization', 'Bearer ' . $token)
            ->getJson("/api/commands/{$command->cmd_id}/status");
        
        $response->assertStatus(403)
            ->assertJson([
                'status' => 'error',
                'code' => 'FORBIDDEN',
                'message' => 'Access denied',
            ]);
    }
}

