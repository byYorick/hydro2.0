<?php

namespace Tests\Feature;

use App\Models\ChannelBinding;
use App\Models\DeviceNode;
use App\Models\InfrastructureInstance;
use App\Models\NodeChannel;
use App\Models\User;
use App\Models\Zone;
use Tests\RefreshDatabase;
use Tests\TestCase;

class SetupWizardValidateDevicesTest extends TestCase
{
    use RefreshDatabase;

    public function test_it_validates_required_device_roles_successfully(): void
    {
        $user = User::factory()->create(['role' => 'agronomist']);
        $zone = Zone::factory()->create();

        $irrigationNode = DeviceNode::factory()->create([
            'uid' => 'nd-test-irrig-1',
            'type' => 'irrig',
            'zone_id' => null,
        ]);
        NodeChannel::query()->create([
            'node_id' => $irrigationNode->id,
            'channel' => 'pump_irrigation',
            'type' => 'ACTUATOR',
        ]);

        $phCorrectionNode = DeviceNode::factory()->create([
            'uid' => 'nd-test-ph-1',
            'type' => 'ph',
            'zone_id' => null,
        ]);
        NodeChannel::query()->create([
            'node_id' => $phCorrectionNode->id,
            'channel' => 'pump_acid',
            'type' => 'ACTUATOR',
        ]);

        $ecCorrectionNode = DeviceNode::factory()->create([
            'uid' => 'nd-test-ec-1',
            'type' => 'ec',
            'zone_id' => null,
        ]);
        NodeChannel::query()->create([
            'node_id' => $ecCorrectionNode->id,
            'channel' => 'pump_a',
            'type' => 'ACTUATOR',
        ]);

        $response = $this->actingAs($user)->postJson('/api/setup-wizard/validate-devices', [
            'zone_id' => $zone->id,
            'assignments' => [
                'irrigation' => $irrigationNode->id,
                'ph_correction' => $phCorrectionNode->id,
                'ec_correction' => $ecCorrectionNode->id,
                'accumulation' => null,
                'climate' => null,
                'light' => null,
            ],
            'selected_node_ids' => [
                $irrigationNode->id,
                $phCorrectionNode->id,
                $ecCorrectionNode->id,
            ],
        ]);

        $response
            ->assertOk()
            ->assertJsonPath('status', 'ok')
            ->assertJsonPath('data.validated', true)
            ->assertJsonPath('data.required_roles.irrigation', $irrigationNode->id)
            ->assertJsonPath('data.required_roles.ph_correction', $phCorrectionNode->id)
            ->assertJsonPath('data.required_roles.ec_correction', $ecCorrectionNode->id)
            ->assertJsonPath('data.required_roles.accumulation', $irrigationNode->id);
    }

    public function test_it_rejects_wrong_node_for_required_role(): void
    {
        $user = User::factory()->create(['role' => 'agronomist']);
        $zone = Zone::factory()->create();

        $irrigationNode = DeviceNode::factory()->create([
            'uid' => 'nd-test-irrig-1',
            'type' => 'irrig',
            'zone_id' => null,
        ]);
        NodeChannel::query()->create([
            'node_id' => $irrigationNode->id,
            'channel' => 'pump_irrigation',
            'type' => 'ACTUATOR',
        ]);

        $ecCorrectionNode = DeviceNode::factory()->create([
            'uid' => 'nd-test-ec-1',
            'type' => 'ec',
            'zone_id' => null,
        ]);
        NodeChannel::query()->create([
            'node_id' => $ecCorrectionNode->id,
            'channel' => 'pump_a',
            'type' => 'ACTUATOR',
        ]);

        $wrongPhNode = DeviceNode::factory()->create([
            'uid' => 'nd-test-light-1',
            'type' => 'light',
            'zone_id' => null,
        ]);
        NodeChannel::query()->create([
            'node_id' => $wrongPhNode->id,
            'channel' => 'light_main',
            'type' => 'ACTUATOR',
        ]);

        $response = $this->actingAs($user)->postJson('/api/setup-wizard/validate-devices', [
            'zone_id' => $zone->id,
            'assignments' => [
                'irrigation' => $irrigationNode->id,
                'ph_correction' => $wrongPhNode->id,
                'ec_correction' => $ecCorrectionNode->id,
                'accumulation' => null,
                'climate' => null,
                'light' => null,
            ],
        ]);

        $response
            ->assertStatus(422)
            ->assertJsonPath('message', 'Validation failed');

        $errors = $response->json('errors');
        $this->assertIsArray($errors);
        $this->assertArrayHasKey('assignments.ph_correction', $errors);
    }

    public function test_it_applies_device_bindings_for_selected_roles(): void
    {
        $user = User::factory()->create(['role' => 'agronomist']);
        $zone = Zone::factory()->create();

        $irrigationNode = DeviceNode::factory()->create([
            'uid' => 'nd-test-irrig-1',
            'type' => 'irrig',
            'zone_id' => null,
        ]);
        $irrigationChannel = NodeChannel::query()->create([
            'node_id' => $irrigationNode->id,
            'channel' => 'pump_irrigation',
            'type' => 'ACTUATOR',
        ]);
        $drainChannel = NodeChannel::query()->create([
            'node_id' => $irrigationNode->id,
            'channel' => 'valve_solution_supply',
            'type' => 'ACTUATOR',
        ]);

        $phCorrectionNode = DeviceNode::factory()->create([
            'uid' => 'nd-test-ph-1',
            'type' => 'ph',
            'zone_id' => null,
        ]);
        $phAcidChannel = NodeChannel::query()->create([
            'node_id' => $phCorrectionNode->id,
            'channel' => 'pump_acid',
            'type' => 'ACTUATOR',
        ]);
        $phBaseChannel = NodeChannel::query()->create([
            'node_id' => $phCorrectionNode->id,
            'channel' => 'pump_base',
            'type' => 'ACTUATOR',
        ]);

        $ecCorrectionNode = DeviceNode::factory()->create([
            'uid' => 'nd-test-ec-1',
            'type' => 'ec',
            'zone_id' => null,
        ]);
        $ecAChannel = NodeChannel::query()->create([
            'node_id' => $ecCorrectionNode->id,
            'channel' => 'pump_a',
            'type' => 'ACTUATOR',
        ]);
        $ecBChannel = NodeChannel::query()->create([
            'node_id' => $ecCorrectionNode->id,
            'channel' => 'pump_b',
            'type' => 'ACTUATOR',
        ]);
        $ecCChannel = NodeChannel::query()->create([
            'node_id' => $ecCorrectionNode->id,
            'channel' => 'pump_c',
            'type' => 'ACTUATOR',
        ]);
        $ecDChannel = NodeChannel::query()->create([
            'node_id' => $ecCorrectionNode->id,
            'channel' => 'pump_d',
            'type' => 'ACTUATOR',
        ]);

        $climateNode = DeviceNode::factory()->create([
            'uid' => 'nd-test-climate-1',
            'type' => 'climate',
            'zone_id' => null,
        ]);
        $ventChannel = NodeChannel::query()->create([
            'node_id' => $climateNode->id,
            'channel' => 'fan_air',
            'type' => 'ACTUATOR',
        ]);
        $heaterChannel = NodeChannel::query()->create([
            'node_id' => $climateNode->id,
            'channel' => 'heater_air',
            'type' => 'ACTUATOR',
        ]);

        $lightNode = DeviceNode::factory()->create([
            'uid' => 'nd-test-light-1',
            'type' => 'light',
            'zone_id' => null,
        ]);
        $lightChannel = NodeChannel::query()->create([
            'node_id' => $lightNode->id,
            'channel' => 'white_light',
            'type' => 'ACTUATOR',
        ]);

        $response = $this->actingAs($user)->postJson('/api/setup-wizard/apply-device-bindings', [
            'zone_id' => $zone->id,
            'assignments' => [
                'irrigation' => $irrigationNode->id,
                'ph_correction' => $phCorrectionNode->id,
                'ec_correction' => $ecCorrectionNode->id,
                'accumulation' => null,
                'climate' => $climateNode->id,
                'light' => $lightNode->id,
            ],
            'selected_node_ids' => [
                $irrigationNode->id,
                $phCorrectionNode->id,
                $ecCorrectionNode->id,
                $climateNode->id,
                $lightNode->id,
            ],
        ]);

        $response
            ->assertOk()
            ->assertJsonPath('status', 'ok')
            ->assertJsonPath('data.validated', true)
            ->assertJsonCount(11, 'data.applied_bindings');

        $zoneBindingRoles = ChannelBinding::query()
            ->whereHas('infrastructureInstance', function ($query) use ($zone) {
                $query->where('owner_type', 'zone')->where('owner_id', $zone->id);
            })
            ->pluck('role')
            ->all();

        $this->assertEqualsCanonicalizing([
            'main_pump',
            'drain',
            'ph_acid_pump',
            'ph_base_pump',
            'ec_npk_pump',
            'ec_calcium_pump',
            'ec_magnesium_pump',
            'ec_micro_pump',
            'vent',
            'heater',
            'light',
        ], $zoneBindingRoles);

        $this->assertDatabaseHas('channel_bindings', [
            'node_channel_id' => $irrigationChannel->id,
            'role' => 'main_pump',
        ]);
        $this->assertDatabaseHas('channel_bindings', [
            'node_channel_id' => $drainChannel->id,
            'role' => 'drain',
        ]);
        $this->assertDatabaseHas('channel_bindings', [
            'node_channel_id' => $phAcidChannel->id,
            'role' => 'ph_acid_pump',
        ]);
        $this->assertDatabaseHas('channel_bindings', [
            'node_channel_id' => $phBaseChannel->id,
            'role' => 'ph_base_pump',
        ]);
        $this->assertDatabaseHas('channel_bindings', [
            'node_channel_id' => $ecAChannel->id,
            'role' => 'ec_npk_pump',
        ]);
        $this->assertDatabaseHas('channel_bindings', [
            'node_channel_id' => $ecBChannel->id,
            'role' => 'ec_calcium_pump',
        ]);
        $this->assertDatabaseHas('channel_bindings', [
            'node_channel_id' => $ecCChannel->id,
            'role' => 'ec_magnesium_pump',
        ]);
        $this->assertDatabaseHas('channel_bindings', [
            'node_channel_id' => $ecDChannel->id,
            'role' => 'ec_micro_pump',
        ]);
        $this->assertDatabaseHas('channel_bindings', [
            'node_channel_id' => $ventChannel->id,
            'role' => 'vent',
        ]);
        $this->assertDatabaseHas('channel_bindings', [
            'node_channel_id' => $heaterChannel->id,
            'role' => 'heater',
        ]);
        $this->assertDatabaseHas('channel_bindings', [
            'node_channel_id' => $lightChannel->id,
            'role' => 'light',
        ]);

        $instancesCount = InfrastructureInstance::query()
            ->where('owner_type', 'zone')
            ->where('owner_id', $zone->id)
            ->count();
        $this->assertSame(11, $instancesCount);
    }
}
