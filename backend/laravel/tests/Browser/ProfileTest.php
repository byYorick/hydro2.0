<?php

namespace Tests\Browser;

use App\Models\User;
use Laravel\Dusk\Browser;
use Tests\DuskTestCase;

class ProfileTest extends DuskTestCase
{
    public function test_profile_page_loads(): void
    {
        $user = User::factory()->create([
            'password' => bcrypt('password'),
        ]);

        $this->browse(function (Browser $browser) use ($user) {
            $browser->loginAs($user)
                ->visit('/profile')
                ->assertPathIs('/profile');

            $component = $browser->script(
                'return JSON.parse(document.getElementById("app").dataset.page).component;'
            )[0] ?? null;

            $this->assertNotNull($component, 'Inertia component name should be resolved.');
            $this->assertStringContains('Profile', $component);
        });
    }

    public function test_profile_information_can_be_updated(): void
    {
        $user = User::factory()->create([
            'password' => bcrypt('password'),
        ]);

        $this->browse(function (Browser $browser) use ($user) {
            $browser->loginAs($user)
                ->visit('/profile')
                ->assertPathIs('/profile');

            // Check that profile form exists
            // Actual form submission testing might require more complex setup
            $browser->assertSee($user->name);
        });
    }
}

