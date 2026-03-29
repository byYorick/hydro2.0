<?php

namespace Tests\Feature;

use App\Models\Greenhouse;
use App\Models\User;
use App\Models\Zone;
use Tests\RefreshDatabase;
use Tests\TestCase;

class SettingsUsersApiTest extends TestCase
{
    use RefreshDatabase;

    public function test_admin_can_create_and_update_user_via_settings_api(): void
    {
        $admin = User::factory()->create(['role' => 'admin']);
        $greenhouse = Greenhouse::factory()->create();
        $zone = Zone::factory()->create(['greenhouse_id' => $greenhouse->id]);

        $create = $this->actingAs($admin)->postJson('/settings/users', [
            'name' => 'Новый оператор',
            'email' => 'new-operator@example.com',
            'password' => 'password123',
            'role' => 'operator',
        ]);

        $create
            ->assertCreated()
            ->assertJsonPath('status', 'ok')
            ->assertJsonPath('data.email', 'new-operator@example.com')
            ->assertJsonMissingPath('data.password');

        $userId = (int) $create->json('data.id');

        $this->assertDatabaseHas('user_greenhouses', [
            'user_id' => $userId,
            'greenhouse_id' => $greenhouse->id,
        ]);
        $this->assertDatabaseHas('user_zones', [
            'user_id' => $userId,
            'zone_id' => $zone->id,
        ]);

        $update = $this->actingAs($admin)->patchJson("/settings/users/{$userId}", [
            'name' => 'Обновленный оператор',
            'email' => 'updated-operator@example.com',
            'role' => 'operator',
        ]);

        $update
            ->assertOk()
            ->assertJsonPath('status', 'ok')
            ->assertJsonPath('data.name', 'Обновленный оператор')
            ->assertJsonPath('data.email', 'updated-operator@example.com');
    }

    public function test_admin_can_manage_agronomist_user_via_settings_api(): void
    {
        $admin = User::factory()->create(['role' => 'admin']);

        $create = $this->actingAs($admin)->postJson('/settings/users', [
            'name' => 'Агроном',
            'email' => 'agronomist-user@example.com',
            'password' => 'password123',
            'role' => 'agronomist',
        ]);

        $create
            ->assertCreated()
            ->assertJsonPath('status', 'ok')
            ->assertJsonPath('data.email', 'agronomist-user@example.com')
            ->assertJsonPath('data.role', 'agronomist');

        $userId = (int) $create->json('data.id');

        $update = $this->actingAs($admin)->patchJson("/settings/users/{$userId}", [
            'name' => 'Инженер автоматики',
            'email' => 'automation-engineer@example.com',
            'role' => 'engineer',
        ]);

        $update
            ->assertOk()
            ->assertJsonPath('status', 'ok')
            ->assertJsonPath('data.name', 'Инженер автоматики')
            ->assertJsonPath('data.email', 'automation-engineer@example.com')
            ->assertJsonPath('data.role', 'engineer');
    }

    public function test_admin_cannot_delete_self_via_settings_api(): void
    {
        $admin = User::factory()->create(['role' => 'admin']);

        $response = $this->actingAs($admin)->deleteJson("/settings/users/{$admin->id}");

        $response
            ->assertStatus(422)
            ->assertJsonPath('status', 'error')
            ->assertJsonPath('message', 'Нельзя удалить самого себя');

        $this->assertNotNull($admin->fresh());
    }
}
