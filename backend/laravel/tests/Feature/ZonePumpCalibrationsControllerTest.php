<?php

namespace Tests\Feature;

use App\Models\DeviceNode;
use App\Models\NodeChannel;
use App\Models\User;
use App\Models\Zone;
use App\Services\AutomationConfigDocumentService;
use App\Services\AutomationConfigRegistry;
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
            'config' => [],
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
            'role' => 'pump_acid',
            'created_at' => now(),
            'updated_at' => now(),
        ]);

        $documents = app(AutomationConfigDocumentService::class);
        $config = $documents->getSystemPayloadByLegacyNamespace('pump_calibration', true);
        $config['ml_per_sec_max'] = 5.2;
        $documents->upsertDocument(
            AutomationConfigRegistry::NAMESPACE_SYSTEM_PUMP_CALIBRATION_POLICY,
            AutomationConfigRegistry::SCOPE_SYSTEM,
            0,
            $config,
            null,
            'test'
        );

        $this->putJson("/api/zones/{$zone->id}/pump-calibrations/{$channel->id}", [
            'ml_per_sec' => 6.0,
        ])->assertStatus(422);

        $this->putJson("/api/zones/{$zone->id}/pump-calibrations/{$channel->id}", [
            'ml_per_sec' => 5.0,
        ])->assertOk();

        $this->assertDatabaseHas('pump_calibrations', [
            'node_channel_id' => $channel->id,
            'component' => 'ph_down',
            'ml_per_sec' => 5.0,
            'source' => 'manual_calibration',
            'is_active' => true,
        ]);

        $this->assertDatabaseHas('zone_events', [
            'zone_id' => $zone->id,
            'type' => 'PUMP_CALIBRATION_FINISHED',
        ]);
    }

    public function test_index_returns_component_from_binding_role_without_legacy_channel_config(): void
    {
        $zone = Zone::factory()->create();
        $node = DeviceNode::factory()->create([
            'zone_id' => $zone->id,
            'status' => 'online',
        ]);
        $channel = NodeChannel::query()->create([
            'node_id' => $node->id,
            'channel' => 'pump_a',
            'type' => 'actuator',
            'metric' => 'PUMP',
            'unit' => '',
            'config' => [],
        ]);

        $infraId = DB::table('infrastructure_instances')->insertGetId([
            'owner_type' => 'zone',
            'owner_id' => $zone->id,
            'asset_type' => 'PUMP',
            'label' => 'EC NPK Pump',
            'required' => true,
            'created_at' => now(),
            'updated_at' => now(),
        ]);

        DB::table('channel_bindings')->insert([
            'infrastructure_instance_id' => $infraId,
            'node_channel_id' => $channel->id,
            'direction' => 'actuator',
            'role' => 'pump_a',
            'created_at' => now(),
            'updated_at' => now(),
        ]);

        $response = $this->getJson("/api/zones/{$zone->id}/pump-calibrations");

        $response->assertOk()
            ->assertJsonPath('data.0.node_channel_id', $channel->id)
            ->assertJsonPath('data.0.role', 'pump_a')
            ->assertJsonPath('data.0.component', 'npk');
    }

    public function test_index_includes_pending_zone_channel_with_active_calibration_without_binding(): void
    {
        $zone = Zone::factory()->create();
        $node = DeviceNode::factory()->create([
            'zone_id' => null,
            'pending_zone_id' => $zone->id,
            'status' => 'online',
        ]);
        $channel = NodeChannel::query()->create([
            'node_id' => $node->id,
            'channel' => 'pump_pending',
            'type' => 'actuator',
            'metric' => 'PUMP',
            'unit' => '',
            'config' => [],
        ]);

        DB::table('pump_calibrations')->insert([
            'node_channel_id' => $channel->id,
            'component' => 'npk',
            'ml_per_sec' => 0.75,
            'source' => 'manual_calibration',
            'valid_from' => now(),
            'is_active' => true,
            'created_at' => now(),
            'updated_at' => now(),
        ]);

        $response = $this->getJson("/api/zones/{$zone->id}/pump-calibrations");

        $response->assertOk()
            ->assertJsonPath('data.0.node_channel_id', $channel->id)
            ->assertJsonPath('data.0.role', 'pump_a')
            ->assertJsonPath('data.0.component', 'npk')
            ->assertJsonPath('data.0.ml_per_sec', 0.75);
    }

    public function test_index_excludes_main_irrigation_pump_even_if_legacy_calibration_exists(): void
    {
        $zone = Zone::factory()->create();
        $node = DeviceNode::factory()->create([
            'zone_id' => $zone->id,
            'status' => 'online',
        ]);
        $channel = NodeChannel::query()->create([
            'node_id' => $node->id,
            'channel' => 'pump_main',
            'type' => 'actuator',
            'metric' => 'PUMP',
            'unit' => '',
            'config' => [],
        ]);

        $infraId = DB::table('infrastructure_instances')->insertGetId([
            'owner_type' => 'zone',
            'owner_id' => $zone->id,
            'asset_type' => 'PUMP',
            'label' => 'Main Irrigation Pump',
            'required' => true,
            'created_at' => now(),
            'updated_at' => now(),
        ]);

        DB::table('channel_bindings')->insert([
            'infrastructure_instance_id' => $infraId,
            'node_channel_id' => $channel->id,
            'direction' => 'actuator',
            'role' => 'pump_main',
            'created_at' => now(),
            'updated_at' => now(),
        ]);

        DB::table('pump_calibrations')->insert([
            'node_channel_id' => $channel->id,
            'component' => 'unknown',
            'ml_per_sec' => 1.0,
            'source' => 'manual_calibration',
            'valid_from' => now(),
            'is_active' => true,
            'created_at' => now(),
            'updated_at' => now(),
        ]);

        $response = $this->getJson("/api/zones/{$zone->id}/pump-calibrations");

        $response->assertOk()
            ->assertJsonCount(0, 'data');
    }

    public function test_index_auto_binds_dosing_channels_by_actuator_type(): void
    {
        $zone = Zone::factory()->create();
        $node = DeviceNode::factory()->create([
            'zone_id' => $zone->id,
            'status' => 'online',
        ]);
        $channel = NodeChannel::query()->create([
            'node_id' => $node->id,
            'channel' => 'ch-generic-1',
            'type' => 'actuator',
            'metric' => 'PUMP',
            'unit' => '',
            'config' => ['actuator_type' => 'pump_b'],
        ]);

        $response = $this->getJson("/api/zones/{$zone->id}/pump-calibrations");

        $response->assertOk()
            ->assertJsonPath('data.0.node_channel_id', $channel->id)
            ->assertJsonPath('data.0.role', 'pump_b')
            ->assertJsonPath('data.0.component', 'calcium');

        $this->assertDatabaseHas('channel_bindings', [
            'node_channel_id' => $channel->id,
            'role' => 'pump_b',
            'direction' => 'actuator',
        ]);
    }
}
