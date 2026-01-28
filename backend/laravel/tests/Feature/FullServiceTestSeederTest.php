<?php

namespace Tests\Feature;

use App\Models\ChannelBinding;
use App\Models\InfrastructureInstance;
use App\Models\Zone;
use Database\Seeders\FullServiceTestSeeder;
use Tests\RefreshDatabase;
use Tests\TestCase;

class FullServiceTestSeederTest extends TestCase
{
    use RefreshDatabase;

    public function test_full_service_seeder_creates_infrastructure_and_capabilities(): void
    {
        $this->seed(FullServiceTestSeeder::class);

        $this->assertGreaterThan(0, InfrastructureInstance::count());
        $this->assertGreaterThan(0, ChannelBinding::count());

        $zones = Zone::all();
        $this->assertNotEmpty($zones);

        $hasAutomationCapabilities = $zones->contains(function (Zone $zone): bool {
            $capabilities = $zone->capabilities ?? [];

            return ! empty($capabilities['irrigation_control'])
                || ! empty($capabilities['light_control'])
                || ! empty($capabilities['climate_control']);
        });

        $this->assertTrue($hasAutomationCapabilities);
    }
}
