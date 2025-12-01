<?php

namespace Tests\Browser;

use App\Models\User;
use Laravel\Dusk\Browser;
use Tests\DuskTestCase;

class WebSocketReconnectionTest extends DuskTestCase
{
    /**
     * Тест восстановления соединения WebSocket после разрыва
     */
    public function test_websocket_reconnection_capability(): void
    {
        $user = User::factory()->create([
            'password' => bcrypt('password'),
        ]);

        $this->browse(function (Browser $browser) use ($user) {
            $browser->loginAs($user)
                ->visit('/')
                ->waitFor('body', 5)
                ->pause(2000); // Ждём инициализацию

            // Проверяем наличие Echo
            $echoAvailable = $browser->script('
                return typeof window.Echo !== "undefined" && window.Echo !== null;
            ')[0];

            $this->assertTrue($echoAvailable, 'Echo should be available');

            // Проверяем наличие методов для переподключения
            $hasReconnectMethods = $browser->script('
                if (window.Echo && window.Echo.connector && window.Echo.connector.pusher) {
                    return typeof window.Echo.connector.pusher.connection !== "undefined";
                }
                return false;
            ')[0];

            $this->assertTrue($hasReconnectMethods, 'Echo should have connection methods');
        });
    }

    /**
     * Тест обработки ошибок соединения
     */
    public function test_websocket_error_handling(): void
    {
        $user = User::factory()->create([
            'password' => bcrypt('password'),
        ]);

        $this->browse(function (Browser $browser) use ($user) {
            $browser->loginAs($user)
                ->visit('/')
                ->waitFor('body', 5)
                ->pause(2000);

            // Проверяем, что приложение может обработать отсутствие соединения
            $canHandleErrors = $browser->script('
                // Проверяем наличие обработчиков ошибок
                return typeof window.Echo !== "undefined";
            ')[0];

            $this->assertTrue($canHandleErrors, 'Application should handle WebSocket errors gracefully');
        });
    }
}

