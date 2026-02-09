<?php

namespace Tests\Feature;

use App\Models\DeviceNode;
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
            'type' => 'pump_node',
            'zone_id' => null,
        ]);
        NodeChannel::query()->create([
            'node_id' => $irrigationNode->id,
            'channel' => 'pump_irrigation',
            'type' => 'ACTUATOR',
        ]);

        $correctionNode = DeviceNode::factory()->create([
            'uid' => 'nd-test-ph-1',
            'type' => 'ph_node',
            'zone_id' => null,
        ]);
        NodeChannel::query()->create([
            'node_id' => $correctionNode->id,
            'channel' => 'pump_acid',
            'type' => 'ACTUATOR',
        ]);

        $accumulationNode = DeviceNode::factory()->create([
            'uid' => 'nd-test-tank-1',
            'type' => 'water_sensor_node',
            'zone_id' => null,
        ]);
        NodeChannel::query()->create([
            'node_id' => $accumulationNode->id,
            'channel' => 'water_level',
            'type' => 'SENSOR',
        ]);

        $response = $this->actingAs($user)->postJson('/api/setup-wizard/validate-devices', [
            'zone_id' => $zone->id,
            'assignments' => [
                'irrigation' => $irrigationNode->id,
                'correction' => $correctionNode->id,
                'accumulation' => $accumulationNode->id,
                'climate' => null,
                'light' => null,
            ],
            'selected_node_ids' => [
                $irrigationNode->id,
                $correctionNode->id,
                $accumulationNode->id,
            ],
        ]);

        $response
            ->assertOk()
            ->assertJsonPath('status', 'ok')
            ->assertJsonPath('data.validated', true)
            ->assertJsonPath('data.required_roles.irrigation', $irrigationNode->id)
            ->assertJsonPath('data.required_roles.correction', $correctionNode->id)
            ->assertJsonPath('data.required_roles.accumulation', $accumulationNode->id);
    }

    public function test_it_rejects_wrong_node_for_required_role(): void
    {
        $user = User::factory()->create(['role' => 'agronomist']);
        $zone = Zone::factory()->create();

        $irrigationNode = DeviceNode::factory()->create([
            'uid' => 'nd-test-irrig-1',
            'type' => 'pump_node',
            'zone_id' => null,
        ]);
        NodeChannel::query()->create([
            'node_id' => $irrigationNode->id,
            'channel' => 'pump_irrigation',
            'type' => 'ACTUATOR',
        ]);

        $accumulationNode = DeviceNode::factory()->create([
            'uid' => 'nd-test-tank-1',
            'type' => 'water_sensor_node',
            'zone_id' => null,
        ]);
        NodeChannel::query()->create([
            'node_id' => $accumulationNode->id,
            'channel' => 'water_level',
            'type' => 'SENSOR',
        ]);

        $response = $this->actingAs($user)->postJson('/api/setup-wizard/validate-devices', [
            'zone_id' => $zone->id,
            'assignments' => [
                'irrigation' => $irrigationNode->id,
                'correction' => $accumulationNode->id,
                'accumulation' => $accumulationNode->id,
                'climate' => null,
                'light' => null,
            ],
        ]);

        $response
            ->assertStatus(422)
            ->assertJsonPath('message', 'Validation failed');

        $errors = $response->json('errors');
        $this->assertIsArray($errors);
        $this->assertArrayHasKey('assignments', $errors);
    }
}
