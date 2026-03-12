<?php

namespace Tests\Feature\Broadcasting;

use App\Models\User;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Tests\TestCase;

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

        // Middleware 'auth' returns 401 before route handler executes
        $response->assertStatus(401);
    }

    public function test_authorizes_authenticated_users_for_zone_command_channels(): void
    {
        $user = User::factory()->create();

        $response = $this->actingAs($user)->postJson('/broadcasting/auth', [
            'channel_name' => 'private-commands.25',
            'socket_id' => '654.321',
        ]);

        $response->assertOk();
        // Broadcast::auth() returns a response that may be empty or contain auth data
        // We just verify it doesn't error
    }
}

