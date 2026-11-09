<?php

namespace Tests\Feature;

use App\Models\DeviceNode;
use App\Models\Sensor;
use App\Models\TelemetryLast;
use App\Models\User;
use App\Models\Zone;
use Tests\RefreshDatabase;
use Tests\TestCase;

class ZoneSnapshotTankLevelTest extends TestCase
{
    use RefreshDatabase;

    public function test_snapshot_level_is_null_when_zone_has_no_level_sensor(): void
    {
        $zone = Zone::factory()->create();
        $user = User::factory()->create(['role' => 'operator']);

        $response = $this->actingAs($user)->getJson("/api/zones/{$zone->id}/snapshot");

        $response->assertOk()
            ->assertJsonPath('data.tank_levels.solution_percent', null)
            ->assertJsonPath('data.tank_levels.clean_percent', null)
            ->assertJsonPath('data.tank_levels.solution_present', false)
            ->assertJsonPath('data.estop.active', false);
    }

    public function test_snapshot_maps_solution_level_switches(): void
    {
        $zone = Zone::factory()->create();
        $node = DeviceNode::factory()->create(['zone_id' => $zone->id]);
        $user = User::factory()->create(['role' => 'operator']);

        foreach (['level_solution_max' => 1.0, 'level_solution_min' => 1.0] as $label => $value) {
            $sensor = Sensor::factory()->create([
                'greenhouse_id' => $zone->greenhouse_id,
                'zone_id' => $zone->id,
                'node_id' => $node->id,
                'type' => 'WATER_LEVEL',
                'label' => $label,
                'is_active' => true,
            ]);
            TelemetryLast::query()->create([
                'sensor_id' => $sensor->id,
                'last_value' => $value,
                'last_ts' => now()->subMinute(),
                'last_quality' => 'GOOD',
            ]);
        }

        $this->actingAs($user)->getJson("/api/zones/{$zone->id}/snapshot")
            ->assertOk()
            ->assertJsonPath('data.tank_levels.solution_percent', 100)
            ->assertJsonPath('data.tank_levels.solution_present', true)
            ->assertJsonPath('data.tank_levels.clean_percent', null);
    }
}
