<?php

namespace Tests\Feature\Broadcasting;

use App\Models\User;
use Tests\RefreshDatabase;
use Tests\TestCase;

class ChannelAuthorizationTest extends TestCase
{
    use RefreshDatabase;

    protected function setUp(): void
    {
        parent::setUp();
        $this->withoutMiddleware([\App\Http\Middleware\VerifyCsrfToken::class]);
    }

    /**
     * Тест авторизации для канала зон
     */
    public function test_authorizes_zone_channel(): void
    {
        $user = User::factory()->create();
        $zone = \App\Models\Zone::factory()->create();

        $response = $this->actingAs($user)->postJson('/broadcasting/auth', [
            'channel_name' => "private-hydro.zones.{$zone->id}",
            'socket_id' => '123.456',
        ]);

        $response->assertOk();
    }

    /**
     * Тест авторизации для канала команд зоны
     */
    public function test_authorizes_commands_zone_channel(): void
    {
        $user = User::factory()->create();
        $zone = \App\Models\Zone::factory()->create();

        $response = $this->actingAs($user)->postJson('/broadcasting/auth', [
            'channel_name' => "private-commands.{$zone->id}",
            'socket_id' => '789.012',
        ]);

        $response->assertOk();
    }

    /**
     * Тест авторизации для глобального канала команд
     */
    public function test_authorizes_global_commands_channel(): void
    {
        $user = User::factory()->create();

        $response = $this->actingAs($user)->postJson('/broadcasting/auth', [
            'channel_name' => 'private-commands.global',
            'socket_id' => '345.678',
        ]);

        $response->assertOk();
    }

    /**
     * Тест авторизации для глобального канала событий
     */
    public function test_authorizes_global_events_channel(): void
    {
        $user = User::factory()->create();

        $response = $this->actingAs($user)->postJson('/broadcasting/auth', [
            'channel_name' => 'private-events.global',
            'socket_id' => '901.234',
        ]);

        $response->assertOk();
    }

    /**
     * Тест авторизации для канала устройств
     */
    public function test_authorizes_devices_channel(): void
    {
        $user = User::factory()->create();

        $response = $this->actingAs($user)->postJson('/broadcasting/auth', [
            'channel_name' => 'private-hydro.devices',
            'socket_id' => '567.890',
        ]);

        $response->assertOk();
    }

    /**
     * Тест авторизации для канала алертов
     */
    public function test_authorizes_alerts_channel(): void
    {
        $user = User::factory()->create();

        $response = $this->actingAs($user)->postJson('/broadcasting/auth', [
            'channel_name' => 'private-hydro.alerts',
            'socket_id' => '234.567',
        ]);

        $response->assertOk();
    }

    /**
     * Тест отклонения авторизации для неавторизованных пользователей
     */
    public function test_rejects_authorization_for_guests(): void
    {
        $response = $this->postJson('/broadcasting/auth', [
            'channel_name' => 'private-hydro.zones.1',
            'socket_id' => '123.456',
        ]);

        // В тестах middleware возвращает 403 вместо 401
        $response->assertStatus(403);
    }

    /**
     * Тест авторизации для разных зон одним пользователем
     */
    public function test_authorizes_multiple_zone_channels(): void
    {
        $user = User::factory()->create();
        $zones = \App\Models\Zone::factory()->count(3)->create();

        foreach ($zones as $zone) {
            $response = $this->actingAs($user)->postJson('/broadcasting/auth', [
                'channel_name' => "private-hydro.zones.{$zone->id}",
                'socket_id' => '123.456',
            ]);

            $response->assertOk();
        }
    }

    /**
     * Тест авторизации для разных каналов команд зон
     */
    public function test_authorizes_multiple_command_channels(): void
    {
        $user = User::factory()->create();
        $zones = \App\Models\Zone::factory()->count(3)->create();

        foreach ($zones as $zone) {
            $response = $this->actingAs($user)->postJson('/broadcasting/auth', [
                'channel_name' => "private-commands.{$zone->id}",
                'socket_id' => '123.456',
            ]);

            $response->assertOk();
        }
    }
}

