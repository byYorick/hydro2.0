<?php

namespace Tests\Feature;

use App\Models\DeviceNode;
use App\Models\Sensor;
use App\Models\TelemetryLast;
use App\Models\User;
use App\Models\Zone;
use Inertia\Testing\AssertableInertia;
use Tests\RefreshDatabase;
use Tests\TestCase;

class ZoneTelemetryPageSelectionTest extends TestCase
{
    use RefreshDatabase;

    public function test_zones_index_uses_air_temperature_in_zone_telemetry_props(): void
    {
        $user = User::factory()->create(['role' => 'admin']);
        $zone = $this->createZoneWithTemperatureTelemetry(20.2, 25.6);

        $this->actingAs($user)
            ->get('/zones')
            ->assertStatus(200)
            ->assertInertia(function (AssertableInertia $page) use ($zone): void {
                $page->component('Zones/Index')
                    ->has('zones', 1)
                    ->where('zones.0.id', $zone->id)
                    ->where('zones.0.telemetry.temperature', 25.6);
            });
    }

    public function test_zone_show_uses_air_temperature_in_telemetry_props(): void
    {
        $user = User::factory()->create(['role' => 'admin']);
        $zone = $this->createZoneWithTemperatureTelemetry(19.7, 24.3);

        $this->actingAs($user)
            ->get("/zones/{$zone->id}")
            ->assertStatus(200)
            ->assertInertia(function (AssertableInertia $page): void {
                $page->component('Zones/Show')
                    ->where('telemetry.temperature', 24.3);
            });
    }

    private function createZoneWithTemperatureTelemetry(float $solutionTemp, float $airTemp): Zone
    {
        $zone = Zone::factory()->create();
        $node = DeviceNode::factory()->create(['zone_id' => $zone->id]);

        $solutionSensor = Sensor::query()->create([
            'greenhouse_id' => $zone->greenhouse_id,
            'zone_id' => $zone->id,
            'node_id' => $node->id,
            'scope' => 'inside',
            'type' => 'TEMPERATURE',
            'label' => 'solution_temp_c',
            'unit' => '°C',
            'specs' => null,
            'is_active' => true,
        ]);

        $airSensor = Sensor::query()->create([
            'greenhouse_id' => $zone->greenhouse_id,
            'zone_id' => $zone->id,
            'node_id' => $node->id,
            'scope' => 'inside',
            'type' => 'TEMPERATURE',
            'label' => 'air_temp_c',
            'unit' => '°C',
            'specs' => null,
            'is_active' => true,
        ]);

        TelemetryLast::query()->create([
            'sensor_id' => $solutionSensor->id,
            'last_value' => $solutionTemp,
            'last_ts' => now()->subMinute(),
            'last_quality' => 'GOOD',
        ]);

        TelemetryLast::query()->create([
            'sensor_id' => $airSensor->id,
            'last_value' => $airTemp,
            'last_ts' => now(),
            'last_quality' => 'GOOD',
        ]);

        return $zone;
    }
}
