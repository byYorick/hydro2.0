<?php

namespace Tests\Feature;

use App\Models\Greenhouse;
use App\Models\User;
use App\Models\Zone;
use Tests\RefreshDatabase;
use Tests\TestCase;

class UsersApiTest extends TestCase
{
    use RefreshDatabase;

    public function test_admin_can_create_and_update_engineer_user_via_api_resource(): void
    {
        $admin = User::factory()->create(['role' => 'admin']);
        $greenhouse = Greenhouse::factory()->create();
        $zone = Zone::factory()->create(['greenhouse_id' => $greenhouse->id]);

        $create = $this->actingAs($admin)->postJson('/api/users', [
            'name' => 'Инженер сервиса',
            'email' => 'service-engineer@example.com',
            'password' => 'password123',
            'role' => 'engineer',
        ]);

        $create
            ->assertCreated()
            ->assertJsonPath('status', 'ok')
            ->assertJsonPath('data.email', 'service-engineer@example.com')
            ->assertJsonPath('data.role', 'engineer');

        $userId = (int) $create->json('data.id');

        $this->assertDatabaseHas('user_greenhouses', [
            'user_id' => $userId,
            'greenhouse_id' => $greenhouse->id,
        ]);
        $this->assertDatabaseHas('user_zones', [
            'user_id' => $userId,
            'zone_id' => $zone->id,
        ]);

        $update = $this->actingAs($admin)->patchJson("/api/users/{$userId}", [
            'name' => 'Главный агроном',
            'role' => 'agronomist',
        ]);

        $update
            ->assertOk()
            ->assertJsonPath('status', 'ok')
            ->assertJsonPath('data.name', 'Главный агроном')
            ->assertJsonPath('data.role', 'agronomist');
    }
}
