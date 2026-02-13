<?php

namespace Tests\Feature;

use App\Models\User;
use Illuminate\Support\Facades\Event;
use Tests\RefreshDatabase;
use Tests\TestCase;

class SettingsUsersApiTest extends TestCase
{
    use RefreshDatabase;

    protected function setUp(): void
    {
        parent::setUp();
        Event::fake();
    }

    public function test_admin_can_create_and_update_user_via_settings_api(): void
    {
        $admin = User::factory()->create(['role' => 'admin']);

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
