<?php

namespace Tests\Browser;

use App\Models\User;
use Laravel\Dusk\Browser;
use Tests\DuskTestCase;

class AuthenticationTest extends DuskTestCase
{
    public function test_user_can_login_and_redirect_to_dashboard(): void
    {
        $user = User::factory()->create([
            'password' => bcrypt('password'),
        ]);

        $this->browse(function (Browser $browser) use ($user) {
            $browser->visit('/login')
                ->assertPathIs('/login')
                ->waitFor('#email', 5)
                ->type('#email', $user->email)
                ->type('#password', 'password')
                ->press('Войти')
                ->waitForLocation('/', 10)
                ->assertPathIs('/');

            $component = $browser->script(
                'return JSON.parse(document.getElementById("app").dataset.page).component;'
            )[0] ?? null;

            $this->assertNotNull($component, 'Inertia component name should be resolved.');
            $this->assertStringStartsWith('Dashboard', $component);
        });
    }

    public function test_unauthenticated_user_redirected_to_login(): void
    {
        $this->browse(function (Browser $browser) {
            $browser->visit('/')
                ->waitForLocation('/login', 5)
                ->assertPathIs('/login');
        });
    }

    public function test_user_can_logout(): void
    {
        $user = User::factory()->create([
            'password' => bcrypt('password'),
        ]);

        $this->browse(function (Browser $browser) use ($user) {
            $browser->loginAs($user)
                ->visit('/')
                ->assertPathIs('/');

            // Logout via POST request
            $browser->post('/logout')
                ->pause(1000);

            // After logout, visiting protected page should redirect to login
            $browser->visit('/zones')
                ->waitForLocation('/login', 10)
                ->assertPathIs('/login');
        });
    }
}

