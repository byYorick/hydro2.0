<?php

namespace Tests\Unit\Services;

use App\Models\DeviceNode;
use App\Models\NodeChannel;
use App\Models\Zone;
use App\Services\PumpCalibrationNodeConfigMirrorService;
use Illuminate\Support\Facades\DB;
use Tests\RefreshDatabase;
use Tests\TestCase;

class PumpCalibrationNodeConfigMirrorServiceTest extends TestCase
{
    use RefreshDatabase;

    public function test_sync_updates_active_pump_calibration_when_ml_per_second_differs(): void
    {
        $zone = Zone::factory()->create();
        $node = DeviceNode::factory()->create([
            'zone_id' => $zone->id,
            'type' => 'ec',
        ]);
        $channel = NodeChannel::create([
            'node_id' => $node->id,
            'channel' => 'pump_a',
            'type' => 'ACTUATOR',
            'metric' => 'PUMP',
            'config' => [
                'actuator_type' => 'PUMP',
                'ml_per_second' => 2.5,
            ],
        ]);

        DB::table('pump_calibrations')->insert([
            'node_channel_id' => $channel->id,
            'component' => 'npk',
            'ml_per_sec' => 2.0,
            'source' => 'manual_calibration',
            'valid_from' => now()->subDay(),
            'is_active' => true,
            'created_at' => now(),
            'updated_at' => now(),
        ]);

        $service = app(PumpCalibrationNodeConfigMirrorService::class);
        $synced = $service->syncActuatorChannel($channel, 'node_config_publish');

        $this->assertTrue($synced);
        $this->assertDatabaseHas('pump_calibrations', [
            'node_channel_id' => $channel->id,
            'ml_per_sec' => 2.5,
            'source' => 'node_config_publish',
            'is_active' => true,
        ]);
        $this->assertDatabaseHas('pump_calibrations', [
            'node_channel_id' => $channel->id,
            'ml_per_sec' => 2.0,
            'is_active' => false,
        ]);
    }

    public function test_sync_skips_when_values_already_match(): void
    {
        $zone = Zone::factory()->create();
        $node = DeviceNode::factory()->create([
            'zone_id' => $zone->id,
            'type' => 'ec',
        ]);
        $channel = NodeChannel::create([
            'node_id' => $node->id,
            'channel' => 'pump_a',
            'type' => 'ACTUATOR',
            'metric' => 'PUMP',
            'config' => [
                'ml_per_second' => 1.75,
            ],
        ]);

        DB::table('pump_calibrations')->insert([
            'node_channel_id' => $channel->id,
            'component' => 'npk',
            'ml_per_sec' => 1.75,
            'source' => 'manual_calibration',
            'valid_from' => now(),
            'is_active' => true,
            'created_at' => now(),
            'updated_at' => now(),
        ]);

        $service = app(PumpCalibrationNodeConfigMirrorService::class);
        $synced = $service->syncActuatorChannel($channel, 'node_config_publish');

        $this->assertFalse($synced);
        $this->assertSame(1, DB::table('pump_calibrations')->where('node_channel_id', $channel->id)->count());
    }

    public function test_sync_creates_calibration_for_dosing_channel_without_existing_row(): void
    {
        $zone = Zone::factory()->create();
        $node = DeviceNode::factory()->create([
            'zone_id' => $zone->id,
            'type' => 'ph',
        ]);
        $channel = NodeChannel::create([
            'node_id' => $node->id,
            'channel' => 'pump_acid',
            'type' => 'ACTUATOR',
            'metric' => 'PUMP',
            'config' => [
                'ml_per_second' => 0.42,
            ],
        ]);

        $service = app(PumpCalibrationNodeConfigMirrorService::class);
        $synced = $service->syncActuatorChannel($channel, 'node_channel_config_apply');

        $this->assertTrue($synced);
        $this->assertDatabaseHas('pump_calibrations', [
            'node_channel_id' => $channel->id,
            'ml_per_sec' => 0.42,
            'component' => 'ph_down',
            'source' => 'node_channel_config_apply',
            'is_active' => true,
        ]);
    }
}
