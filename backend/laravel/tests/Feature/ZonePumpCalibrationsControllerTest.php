<?php

namespace Tests\Feature;

use App\Models\DeviceNode;
use App\Models\NodeChannel;
use App\Models\SystemAutomationSetting;
use App\Models\User;
use App\Models\Zone;
use Illuminate\Support\Facades\DB;
use Laravel\Sanctum\Sanctum;
use Tests\RefreshDatabase;
use Tests\TestCase;

class ZonePumpCalibrationsControllerTest extends TestCase
{
    use RefreshDatabase;

    protected function setUp(): void
    {
        parent::setUp();

        Sanctum::actingAs(User::factory()->create(['role' => 'admin']));
    }

    public function test_update_uses_dynamic_ml_per_sec_range_from_system_settings(): void
    {
        $zone = Zone::factory()->create();
        $node = DeviceNode::factory()->create([
            'zone_id' => $zone->id,
            'status' => 'online',
        ]);
        $channel = NodeChannel::query()->create([
            'node_id' => $node->id,
            'channel' => 'pump_acid',
            'type' => 'actuator',
            'metric' => 'PUMP',
            'unit' => '',
            'config' => ['pump_calibration' => ['component' => 'ph_down']],
        ]);

        $infraId = DB::table('infrastructure_instances')->insertGetId([
            'owner_type' => 'zone',
            'owner_id' => $zone->id,
            'asset_type' => 'PUMP',
            'label' => 'pH Acid Pump',
            'required' => true,
            'created_at' => now(),
            'updated_at' => now(),
        ]);

        DB::table('channel_bindings')->insert([
            'infrastructure_instance_id' => $infraId,
            'node_channel_id' => $channel->id,
            'direction' => 'actuator',
            'role' => 'ph_acid_pump',
            'created_at' => now(),
            'updated_at' => now(),
        ]);

        $setting = SystemAutomationSetting::query()->firstWhere('namespace', 'pump_calibration');
        $config = $setting->config;
        $config['ml_per_sec_max'] = 2.0;
        $setting->update(['config' => $config]);

        $this->putJson("/api/zones/{$zone->id}/pump-calibrations/{$channel->id}", [
            'ml_per_sec' => 3.0,
        ])->assertStatus(422);

        $this->putJson("/api/zones/{$zone->id}/pump-calibrations/{$channel->id}", [
            'ml_per_sec' => 1.5,
        ])->assertOk();
    }
}
