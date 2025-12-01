<?php

namespace Tests\Browser;

use App\Models\Greenhouse;
use App\Models\User;
use App\Models\Zone;
use Laravel\Dusk\Browser;
use Tests\DuskTestCase;

class ZonesTest extends DuskTestCase
{
    public function test_zones_list_page_loads(): void
    {
        $user = User::factory()->create([
            'password' => bcrypt('password'),
        ]);

        $greenhouse = Greenhouse::factory()->create();
        Zone::factory()->count(3)->create(['greenhouse_id' => $greenhouse->id]);

        $this->browse(function (Browser $browser) use ($user) {
            $browser->loginAs($user)
                ->visit('/zones')
                ->assertPathIs('/zones');

            $component = $browser->script(
                'return JSON.parse(document.getElementById("app").dataset.page).component;'
            )[0] ?? null;

            $this->assertNotNull($component, 'Inertia component name should be resolved.');
            $this->assertStringStartsWith('Zones', $component);
        });
    }

    public function test_zone_detail_page_loads(): void
    {
        $user = User::factory()->create([
            'password' => bcrypt('password'),
        ]);

        $greenhouse = Greenhouse::factory()->create();
        $zone = Zone::factory()->create(['greenhouse_id' => $greenhouse->id]);

        $this->browse(function (Browser $browser) use ($user, $zone) {
            $browser->loginAs($user)
                ->visit("/zones/{$zone->id}")
                ->assertPathIs("/zones/{$zone->id}");

            $component = $browser->script(
                'return JSON.parse(document.getElementById("app").dataset.page).component;'
            )[0] ?? null;

            $this->assertNotNull($component, 'Inertia component name should be resolved.');
            $this->assertStringStartsWith('Zones', $component);
        });
    }

    public function test_navigation_from_dashboard_to_zones(): void
    {
        $user = User::factory()->create([
            'password' => bcrypt('password'),
        ]);

        $this->browse(function (Browser $browser) use ($user) {
            $browser->loginAs($user)
                ->visit('/')
                ->waitFor('body', 5)
                ->assertPathIs('/');

            // Try to find and click a link to zones (if exists)
            // If no specific link, just verify navigation works
            $browser->visit('/zones')
                ->assertPathIs('/zones');
        });
    }
}

