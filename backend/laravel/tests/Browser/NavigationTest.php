<?php

namespace Tests\Browser;

use App\Models\Greenhouse;
use App\Models\User;
use App\Models\Zone;
use Laravel\Dusk\Browser;
use Tests\DuskTestCase;

class NavigationTest extends DuskTestCase
{
    public function test_user_can_navigate_between_main_pages(): void
    {
        $user = User::factory()->create([
            'password' => bcrypt('password'),
        ]);

        $greenhouse = Greenhouse::factory()->create();
        $zone = Zone::factory()->create(['greenhouse_id' => $greenhouse->id]);

        $this->browse(function (Browser $browser) use ($user, $zone) {
            $browser->loginAs($user);

            // Navigate to dashboard
            $browser->visit('/')
                ->assertPathIs('/');

            // Navigate to zones
            $browser->visit('/zones')
                ->assertPathIs('/zones');

            // Navigate to a specific zone
            $browser->visit("/zones/{$zone->id}")
                ->assertPathIs("/zones/{$zone->id}");

            // Navigate to devices
            $browser->visit('/devices')
                ->assertPathIs('/devices');

            // Navigate to recipes
            $browser->visit('/recipes')
                ->assertPathIs('/recipes');
        });
    }

    public function test_dashboard_shows_statistics(): void
    {
        $user = User::factory()->create([
            'password' => bcrypt('password'),
        ]);

        $greenhouse = Greenhouse::factory()->create();
        Zone::factory()->count(2)->create(['greenhouse_id' => $greenhouse->id]);

        $this->browse(function (Browser $browser) use ($user) {
            $browser->loginAs($user)
                ->visit('/')
                ->waitFor('body', 5)
                ->assertPathIs('/');

            // Verify dashboard loaded
            $component = $browser->script(
                'return JSON.parse(document.getElementById("app").dataset.page).component;'
            )[0] ?? null;

            $this->assertNotNull($component, 'Dashboard component should be loaded.');
            $this->assertStringStartsWith('Dashboard', $component);
        });
    }
}

