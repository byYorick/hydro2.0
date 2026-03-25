<?php

namespace Tests\Feature;

use App\Models\User;
use Illuminate\Support\Facades\Event;
use Tests\RefreshDatabase;
use Tests\TestCase;

class UsersApiTest extends TestCase
{
    use RefreshDatabase;

    protected function setUp(): void
    {
        parent::setUp();
        Event::fake();
    }

    public function test_admin_can_create_and_update_engineer_user_via_api_resource(): void
    {
        $admin = User::factory()->create(['role' => 'admin']);

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
