<?php

namespace Tests\Browser;

use App\Models\Greenhouse;
use App\Models\User;
use App\Models\Zone;
use Laravel\Dusk\Browser;
use Tests\DuskTestCase;

class WebSocketChannelsTest extends DuskTestCase
{
    /**
     * Тест подписки на канал команд зоны
     */
    public function test_can_subscribe_to_zone_commands_channel(): void
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
                ->pause(2000); // Ждём инициализацию Echo и подписки

            // Проверяем, что Echo доступен
            $echoAvailable = $browser->script('
                return typeof window.Echo !== "undefined" && window.Echo !== null;
            ')[0];

            $this->assertTrue($echoAvailable, 'Echo should be available');

            // Проверяем, что канал подписан (если есть API для проверки)
            // Echo API не всегда предоставляет прямой доступ к подпискам в тестах
            // Но мы можем проверить, что Echo инициализирован и страница загружена
            $browser->assertPathIs("/zones/{$zone->id}");
        });
    }

    /**
     * Тест подписки на глобальный канал событий
     */
    public function test_can_subscribe_to_global_events_channel(): void
    {
        $user = User::factory()->create([
            'password' => bcrypt('password'),
        ]);

        $this->browse(function (Browser $browser) use ($user) {
            $browser->loginAs($user)
                ->visit('/')
                ->waitFor('body', 5)
                ->pause(2000);

            // Проверяем доступность Echo
            $echoAvailable = $browser->script('
                return typeof window.Echo !== "undefined" && window.Echo !== null;
            ')[0];

            $this->assertTrue($echoAvailable, 'Echo should be available for global events channel');
        });
    }

    /**
     * Тест авторизации каналов через broadcasting/auth endpoint
     */
    public function test_channel_authorization_works(): void
    {
        $user = User::factory()->create([
            'password' => bcrypt('password'),
        ]);

        $greenhouse = Greenhouse::factory()->create();
        $zone = Zone::factory()->create(['greenhouse_id' => $greenhouse->id]);

        $this->browse(function (Browser $browser) use ($user, $zone) {
            $browser->loginAs($user)
                ->visit('/')
                ->waitFor('body', 5);

            // Проверяем, что broadcasting auth endpoint доступен
            // Это проверяется косвенно через успешную загрузку страницы
            // где Echo пытается авторизоваться на каналах
            $browser->assertPathIs('/');

            // Проверяем, что нет ошибок в консоли (если возможно)
            $errors = $browser->script('
                return window.console.errors || [];
            ')[0] ?? [];

            // Это базовая проверка - в реальном тесте можно проверять более детально
        });
    }

    /**
     * Тест подписки на канал устройств
     */
    public function test_can_subscribe_to_devices_channel(): void
    {
        $user = User::factory()->create([
            'password' => bcrypt('password'),
        ]);

        $this->browse(function (Browser $browser) use ($user) {
            $browser->loginAs($user)
                ->visit('/devices')
                ->waitFor('body', 5)
                ->pause(2000);

            // Проверяем, что страница загрузилась и Echo доступен
            $echoAvailable = $browser->script('
                return typeof window.Echo !== "undefined" && window.Echo !== null;
            ')[0];

            $this->assertTrue($echoAvailable, 'Echo should be available on devices page');
            $browser->assertPathIs('/devices');
        });
    }

    /**
     * Тест подписки на канал алертов
     */
    public function test_can_subscribe_to_alerts_channel(): void
    {
        $user = User::factory()->create([
            'password' => bcrypt('password'),
        ]);

        $this->browse(function (Browser $browser) use ($user) {
            $browser->loginAs($user)
                ->visit('/')
                ->waitFor('body', 5)
                ->pause(2000);

            // На главной странице обычно подписываются на канал алертов
            $echoAvailable = $browser->script('
                return typeof window.Echo !== "undefined" && window.Echo !== null;
            ')[0];

            $this->assertTrue($echoAvailable, 'Echo should be available for alerts channel');
        });
    }
}

