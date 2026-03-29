<?php

namespace Tests\Feature;

use App\Models\ChannelBinding;
use App\Models\DeviceNode;
use App\Models\Greenhouse;
use App\Models\InfrastructureInstance;
use App\Models\NodeChannel;
use App\Models\User;
use Tests\RefreshDatabase;
use Tests\TestCase;

class SetupWizardGreenhouseClimateBindingsTest extends TestCase
{
    use RefreshDatabase;

    public function test_it_validates_greenhouse_climate_bindings(): void
    {
        $user = User::factory()->create(['role' => 'agronomist']);
        $greenhouse = Greenhouse::factory()->create();

        $climateSensor = DeviceNode::factory()->create([
            'uid' => 'nd-gh-climate-sensor',
            'type' => 'climate',
        ]);
        NodeChannel::query()->create([
            'node_id' => $climateSensor->id,
            'channel' => 'temp_air',
            'type' => 'SENSOR',
        ]);
        NodeChannel::query()->create([
            'node_id' => $climateSensor->id,
            'channel' => 'humidity_air',
            'type' => 'SENSOR',
        ]);

        $ventActuator = DeviceNode::factory()->create([
            'uid' => 'nd-gh-vent',
            'type' => 'climate',
        ]);
        NodeChannel::query()->create([
            'node_id' => $ventActuator->id,
            'channel' => 'vent_drive',
            'type' => 'ACTUATOR',
        ]);

        $response = $this->actingAs($user)->postJson('/api/setup-wizard/validate-greenhouse-climate-devices', [
            'greenhouse_id' => $greenhouse->id,
            'climate_sensors' => [$climateSensor->id],
            'vent_actuators' => [$ventActuator->id],
            'fan_actuators' => [],
        ]);

        $response->assertOk()
            ->assertJsonPath('status', 'ok')
            ->assertJsonPath('data.validated', true)
            ->assertJsonPath('data.greenhouse_id', $greenhouse->id)
            ->assertJsonPath('data.roles.climate_sensors.0', $climateSensor->id)
            ->assertJsonPath('data.roles.vent_actuators.0', $ventActuator->id);
    }

    public function test_it_applies_greenhouse_climate_bindings(): void
    {
        $user = User::factory()->create(['role' => 'agronomist']);
        $greenhouse = Greenhouse::factory()->create();

        $climateSensor = DeviceNode::factory()->create([
            'uid' => 'nd-gh-climate-sensor',
            'type' => 'climate',
        ]);
        $tempChannel = NodeChannel::query()->create([
            'node_id' => $climateSensor->id,
            'channel' => 'temp_air',
            'type' => 'SENSOR',
        ]);
        $humidityChannel = NodeChannel::query()->create([
            'node_id' => $climateSensor->id,
            'channel' => 'humidity_air',
            'type' => 'SENSOR',
        ]);
        $co2Channel = NodeChannel::query()->create([
            'node_id' => $climateSensor->id,
            'channel' => 'co2_ppm',
            'type' => 'SENSOR',
        ]);

        $weatherSensor = DeviceNode::factory()->create([
            'uid' => 'nd-gh-weather',
            'type' => 'climate',
        ]);
        $windChannel = NodeChannel::query()->create([
            'node_id' => $weatherSensor->id,
            'channel' => 'wind_speed',
            'type' => 'SENSOR',
        ]);

        $ventActuator = DeviceNode::factory()->create([
            'uid' => 'nd-gh-vent',
            'type' => 'climate',
        ]);
        $ventDriveChannel = NodeChannel::query()->create([
            'node_id' => $ventActuator->id,
            'channel' => 'vent_drive',
            'type' => 'ACTUATOR',
        ]);
        $ventPctChannel = NodeChannel::query()->create([
            'node_id' => $ventActuator->id,
            'channel' => 'vent_window_pct',
            'type' => 'ACTUATOR',
        ]);

        $fanActuator = DeviceNode::factory()->create([
            'uid' => 'nd-gh-fan',
            'type' => 'climate',
        ]);
        $fanChannel = NodeChannel::query()->create([
            'node_id' => $fanActuator->id,
            'channel' => 'fan_air',
            'type' => 'ACTUATOR',
        ]);

        $response = $this->actingAs($user)->postJson('/api/setup-wizard/apply-greenhouse-climate-bindings', [
            'greenhouse_id' => $greenhouse->id,
            'climate_sensors' => [$climateSensor->id],
            'weather_station_sensors' => [$weatherSensor->id],
            'vent_actuators' => [$ventActuator->id],
            'fan_actuators' => [$fanActuator->id],
        ]);

        $response->assertOk()
            ->assertJsonPath('status', 'ok')
            ->assertJsonPath('data.validated', true)
            ->assertJsonCount(7, 'data.applied_bindings');

        $bindingRoles = ChannelBinding::query()
            ->whereHas('infrastructureInstance', function ($query) use ($greenhouse) {
                $query->where('owner_type', 'greenhouse')->where('owner_id', $greenhouse->id);
            })
            ->pluck('role')
            ->all();

        $this->assertEqualsCanonicalizing([
            'climate_sensor',
            'climate_sensor',
            'climate_sensor',
            'weather_station_sensor',
            'vent_actuator',
            'vent_actuator',
            'fan_actuator',
        ], $bindingRoles);

        $this->assertDatabaseHas('channel_bindings', [
            'node_channel_id' => $tempChannel->id,
            'role' => 'climate_sensor',
            'direction' => 'sensor',
        ]);
        $this->assertDatabaseHas('channel_bindings', [
            'node_channel_id' => $humidityChannel->id,
            'role' => 'climate_sensor',
            'direction' => 'sensor',
        ]);
        $this->assertDatabaseHas('channel_bindings', [
            'node_channel_id' => $co2Channel->id,
            'role' => 'climate_sensor',
            'direction' => 'sensor',
        ]);
        $this->assertDatabaseHas('channel_bindings', [
            'node_channel_id' => $windChannel->id,
            'role' => 'weather_station_sensor',
            'direction' => 'sensor',
        ]);
        $this->assertDatabaseHas('channel_bindings', [
            'node_channel_id' => $ventDriveChannel->id,
            'role' => 'vent_actuator',
            'direction' => 'actuator',
        ]);
        $this->assertDatabaseHas('channel_bindings', [
            'node_channel_id' => $ventPctChannel->id,
            'role' => 'vent_actuator',
            'direction' => 'actuator',
        ]);
        $this->assertDatabaseHas('channel_bindings', [
            'node_channel_id' => $fanChannel->id,
            'role' => 'fan_actuator',
            'direction' => 'actuator',
        ]);

        $instancesCount = InfrastructureInstance::query()
            ->where('owner_type', 'greenhouse')
            ->where('owner_id', $greenhouse->id)
            ->count();
        $this->assertSame(4, $instancesCount);
    }

    public function test_it_rejects_greenhouse_climate_binding_without_required_roles(): void
    {
        $user = User::factory()->create(['role' => 'agronomist']);
        $greenhouse = Greenhouse::factory()->create();

        $response = $this->actingAs($user)->postJson('/api/setup-wizard/validate-greenhouse-climate-devices', [
            'greenhouse_id' => $greenhouse->id,
            'climate_sensors' => [],
            'vent_actuators' => [],
            'fan_actuators' => [],
        ]);

        $response->assertStatus(422)
            ->assertJsonValidationErrors([
                'climate_sensors',
            ]);
    }
}
