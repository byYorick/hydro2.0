<?php

namespace Tests\Feature\Broadcasting;

use App\Models\User;
use Tests\RefreshDatabase;
use Tests\TestCase;

/**
 * @group skip-in-ci
 * Broadcasting tests require Reverb server to be running
 */
class BroadcastAuthTest extends TestCase
{
    use RefreshDatabase;

    protected function setUp(): void
    {
        parent::setUp();
        $this->withoutMiddleware([\App\Http\Middleware\VerifyCsrfToken::class]);
    }

    public function test_rejects_private_channel_authorization_for_guests(): void
    {
        $response = $this->postJson('/broadcasting/auth', [
            'channel_name' => 'private-hydro.zones.15',
            'socket_id' => '123.456',
        ]);

        // В тестах middleware возвращает 403 вместо 401
        $response->assertStatus(403);
    }

    public function test_authorizes_authenticated_users_for_zone_command_channels(): void
    {
        $user = User::factory()->create(['role' => 'operator']);

        $zone = \App\Models\Zone::factory()->create();
        
        $response = $this->actingAs($user)->postJson('/broadcasting/auth', [
            'channel_name' => "private-commands.{$zone->id}",
            'socket_id' => '654.321',
        ]);

        $response->assertOk();
        // Broadcast::auth() returns a response that may be empty or contain auth data
        // We just verify it doesn't error
    }
}

