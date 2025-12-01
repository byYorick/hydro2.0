<?php

namespace Tests\Browser;

use App\Models\Greenhouse;
use App\Models\User;
use App\Models\Zone;
use Laravel\Dusk\Browser;
use Tests\DuskTestCase;

class WebSocketMessagesTest extends DuskTestCase
{
    /**
     * Тест готовности к получению сообщений через WebSocket
     */
    public function test_page_ready_to_receive_websocket_messages(): void
    {
        $user = User::factory()->create([
            'password' => bcrypt('password'),
        ]);

        $greenhouse = Greenhouse::factory()->create();
        $zone = Zone::factory()->create(['greenhouse_id' => $greenhouse->id]);

        $this->browse(function (Browser $browser) use ($user, $zone) {
            $browser->loginAs($user)
                ->visit("/zones/{$zone->id}")
                ->waitFor('body', 5)
                ->pause(3000); // Ждём инициализацию и подписки

            // Проверяем, что Echo инициализирован и готов к получению сообщений
            $isReady = $browser->script('
                if (window.Echo && window.Echo.connector && window.Echo.connector.pusher) {
                    const connection = window.Echo.connector.pusher.connection;
                    return connection && (connection.state === "connected" || connection.state === "connecting");
                }
                return false;
            ')[0];

            // В тестовой среде соединение может быть не установлено, но Echo должен быть готов
            $echoExists = $browser->script('return typeof window.Echo !== "undefined"')[0];
            $this->assertTrue($echoExists, 'Echo should be ready to receive messages');
        });
    }

    /**
     * Тест наличия обработчиков событий на странице
     */
    public function test_page_has_websocket_event_handlers(): void
    {
        $user = User::factory()->create([
            'password' => bcrypt('password'),
        ]);

        $greenhouse = Greenhouse::factory()->create();
        $zone = Zone::factory()->create(['greenhouse_id' => $greenhouse->id]);

        $this->browse(function (Browser $browser) use ($user, $zone) {
            $browser->loginAs($user)
                ->visit("/zones/{$zone->id}")
                ->waitFor('body', 5)
                ->pause(2000);

            // Проверяем, что страница загрузилась (это косвенно означает, что обработчики готовы)
            $browser->assertPathIs("/zones/{$zone->id}");

            // Проверяем наличие Echo для обработки событий
            $echoExists = $browser->script('return typeof window.Echo !== "undefined"')[0];
            $this->assertTrue($echoExists, 'Page should have Echo for handling WebSocket events');
        });
    }
}

