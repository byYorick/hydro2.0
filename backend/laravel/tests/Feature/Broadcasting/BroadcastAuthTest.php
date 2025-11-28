<?php

use App\Models\User;
use Illuminate\Foundation\Testing\RefreshDatabase;
use function Pest\Laravel\actingAs;
use function Pest\Laravel\postJson;

uses(RefreshDatabase::class);

beforeEach(function () {
    $this->withoutMiddleware([\App\Http\Middleware\VerifyCsrfToken::class]);
});

it('rejects private channel authorization for guests', function () {
    $response = $this->postJson('/broadcasting/auth', [
        'channel_name' => 'private-hydro.zones.15',
        'socket_id' => '123.456',
    ]);

    $response->assertStatus(401);
});

it('authorizes authenticated users for zone command channels', function () {
    $user = User::factory()->create();

    $this->actingAs($user);

    $response = $this->postJson('/broadcasting/auth', [
        'channel_name' => 'private-commands.25',
        'socket_id' => '654.321',
    ]);

    $response->assertOk();
});

