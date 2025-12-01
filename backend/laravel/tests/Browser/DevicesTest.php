<?php

namespace Tests\Browser;

use App\Models\DeviceNode;
use App\Models\Greenhouse;
use App\Models\User;
use App\Models\Zone;
use Laravel\Dusk\Browser;
use Tests\DuskTestCase;

class DevicesTest extends DuskTestCase
{
    public function test_devices_list_page_loads(): void
    {
        $user = User::factory()->create([
            'password' => bcrypt('password'),
        ]);

        $greenhouse = Greenhouse::factory()->create();
        $zone = Zone::factory()->create(['greenhouse_id' => $greenhouse->id]);
        DeviceNode::factory()->count(2)->create(['zone_id' => $zone->id]);

        $this->browse(function (Browser $browser) use ($user) {
            $browser->loginAs($user)
                ->visit('/devices')
                ->assertPathIs('/devices');

            $component = $browser->script(
                'return JSON.parse(document.getElementById("app").dataset.page).component;'
            )[0] ?? null;

            $this->assertNotNull($component, 'Inertia component name should be resolved.');
            $this->assertStringStartsWith('Devices', $component);
        });
    }

    public function test_device_detail_page_loads(): void
    {
        $user = User::factory()->create([
            'password' => bcrypt('password'),
        ]);

        $greenhouse = Greenhouse::factory()->create();
        $zone = Zone::factory()->create(['greenhouse_id' => $greenhouse->id]);
        $device = DeviceNode::factory()->create(['zone_id' => $zone->id]);

        $this->browse(function (Browser $browser) use ($user, $device) {
            $browser->loginAs($user)
                ->visit("/devices/{$device->id}")
                ->assertPathIs("/devices/{$device->id}");

            $component = $browser->script(
                'return JSON.parse(document.getElementById("app").dataset.page).component;'
            )[0] ?? null;

            $this->assertNotNull($component, 'Inertia component name should be resolved.');
            $this->assertStringStartsWith('Devices', $component);
        });
    }
}

