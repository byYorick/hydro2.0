<?php

namespace Tests\Feature;

use App\Models\User;
use Illuminate\Foundation\Testing\RefreshDatabase;
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
        $user = User::factory()->create();
        $this->actingAs($user);
        $token = $user->createToken('t')->plainTextToken;

        $this->withHeader('Authorization', 'Bearer '.$token)
            ->postJson("/api/zones/{$zone->id}/commands", [])
            ->assertStatus(422);
    }
}


