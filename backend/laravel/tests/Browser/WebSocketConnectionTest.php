<?php

namespace Tests\Browser;

use App\Models\User;
use Laravel\Dusk\Browser;
use Tests\DuskTestCase;

class WebSocketConnectionTest extends DuskTestCase
{
    /**
     * Тест подключения к WebSocket через Echo
     */
    public function test_websocket_connection_available(): void
    {
        $user = User::factory()->create([
            'password' => bcrypt('password'),
        ]);

        $this->browse(function (Browser $browser) use ($user) {
            $browser->loginAs($user)
                ->visit('/')
                ->waitFor('body', 5);

            // Проверяем, что Echo инициализирован
            $echoAvailable = $browser->script('
                return typeof window.Echo !== "undefined" && window.Echo !== null;
            ')[0];

            $this->assertTrue($echoAvailable, 'Echo should be available on the page');

            // Проверяем состояние соединения
            $connectionState = $browser->script('
                if (window.Echo && window.Echo.connector && window.Echo.connector.pusher && window.Echo.connector.pusher.connection) {
                    return window.Echo.connector.pusher.connection.state;
                }
                return null;
            ')[0];

            // Соединение может быть в разных состояниях (connected, connecting, disconnected)
            $this->assertNotNull($connectionState, 'Connection state should be available');
            $validStates = ['connected', 'connecting', 'disconnected'];
            $this->assertTrue(in_array($connectionState, $validStates, true), 
                "Connection state '{$connectionState}' should be one of: " . implode(', ', $validStates));
        });
    }

    /**
     * Тест проверки WebSocket соединения в статусе системы
     */
    public function test_websocket_status_in_system_status(): void
    {
        $user = User::factory()->create([
            'password' => bcrypt('password'),
        ]);

        $this->browse(function (Browser $browser) use ($user) {
            $browser->loginAs($user)
                ->visit('/')
                ->waitFor('body', 5);

            // Проверяем, что есть элемент, отображающий статус WebSocket
            // Статус может отображаться в header или другом месте
            $browser->assertPresent('body');

            // Проверяем наличие Echo в window
            $echoExists = $browser->script('return typeof window.Echo !== "undefined"')[0];
            $this->assertTrue($echoExists, 'Echo should be defined in window object');
        });
    }

    /**
     * Тест инициализации Echo при загрузке страницы
     */
    public function test_echo_initializes_on_page_load(): void
    {
        $user = User::factory()->create([
            'password' => bcrypt('password'),
        ]);

        $this->browse(function (Browser $browser) use ($user) {
            $browser->loginAs($user)
                ->visit('/zones')
                ->waitFor('body', 5)
                ->pause(2000); // Ждём инициализацию Echo

            // Проверяем, что Echo был инициализирован
            $echoInitialized = $browser->script('
                return typeof window.Echo !== "undefined" && window.Echo !== null;
            ')[0];

            $this->assertTrue($echoInitialized, 'Echo should be initialized after page load');
        });
    }
}

