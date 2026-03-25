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
            'role' => 'ph_acid_pump',
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
            'is_active' => true,
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
            'role' => 'ec_npk_pump',
            'created_at' => now(),
            'updated_at' => now(),
        ]);

        $response = $this->getJson("/api/zones/{$zone->id}/pump-calibrations");

        $response->assertOk()
            ->assertJsonPath('data.0.node_channel_id', $channel->id)
            ->assertJsonPath('data.0.role', 'ec_npk_pump')
            ->assertJsonPath('data.0.component', 'npk');
    }
}
