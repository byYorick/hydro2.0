<?php

namespace Tests\Feature;

use App\Models\DeviceNode;
use App\Models\Sensor;
use App\Models\TelemetryLast;
use App\Models\TelemetrySample;
use App\Models\User;
use App\Models\Zone;
use Illuminate\Support\Facades\DB;
use Tests\RefreshDatabase;
use Tests\TestCase;

class TelemetryTest extends TestCase
{
    use RefreshDatabase;

    public function test_zone_telemetry_endpoints_require_auth(): void
    {
        $this->getJson('/api/zones/1/telemetry/last')->assertStatus(401);
        $this->getJson('/api/zones/1/telemetry/history')->assertStatus(401);
    }

    public function test_zone_telemetry_history_validation(): void
    {
        $user = User::factory()->create(['role' => 'viewer']);
        $this->actingAs($user);
        $token = $user->createToken('test')->plainTextToken;

        // Создаем зону, чтобы пользователь имел к ней доступ
        $zone = \App\Models\Zone::factory()->create();

        // Запрос без обязательного параметра 'metric' должен вернуть 422
        $resp = $this->withHeader('Authorization', 'Bearer '.$token)
            ->getJson("/api/zones/{$zone->id}/telemetry/history");
        $resp->assertStatus(422);
    }

    public function test_node_telemetry_requires_auth(): void
    {
        $this->getJson('/api/nodes/1/telemetry/last')->assertStatus(401);
    }

    public function test_node_telemetry_allows_access_for_authorized_user(): void
    {
        $user = User::factory()->create(['role' => 'viewer']);
        $this->actingAs($user);
        $token = $user->createToken('test')->plainTextToken;

        $zone = \App\Models\Zone::factory()->create();
        $node = \App\Models\DeviceNode::factory()->create(['zone_id' => $zone->id]);

        $response = $this->withHeader('Authorization', 'Bearer '.$token)
            ->getJson("/api/nodes/{$node->id}/telemetry/last");

        $response->assertOk()
            ->assertJsonStructure(['status', 'data']);
    }

    public function test_zone_telemetry_history_returns_samples(): void
    {
        $user = User::factory()->create(['role' => 'viewer']);
        $this->actingAs($user);
        $token = $user->createToken('test')->plainTextToken;

        $zone = Zone::factory()->create();
        $node = DeviceNode::factory()->create(['zone_id' => $zone->id]);

        $sensor = Sensor::query()->create([
            'greenhouse_id' => $zone->greenhouse_id,
            'zone_id' => $zone->id,
            'node_id' => $node->id,
            'scope' => 'inside',
            'type' => 'PH',
            'label' => 'ph_sensor',
            'unit' => null,
            'specs' => null,
            'is_active' => true,
        ]);

        TelemetrySample::query()->create([
            'sensor_id' => $sensor->id,
            'ts' => now()->subMinute(),
            'zone_id' => $zone->id,
            'cycle_id' => null,
            'value' => 6.5,
            'quality' => 'GOOD',
            'metadata' => ['metric_type' => 'PH', 'channel' => 'ph_sensor'],
        ]);

        $response = $this->withHeader('Authorization', 'Bearer '.$token)
            ->getJson("/api/zones/{$zone->id}/telemetry/history?metric=PH");

        $response->assertOk()
            ->assertJsonPath('status', 'ok');

        $first = $response->json('data.0');
        $this->assertSame('PH', $first['metric_type']);
        $this->assertSame('ph_sensor', $first['channel']);
    }

    public function test_zone_telemetry_last_returns_object(): void
    {
        $user = User::factory()->create(['role' => 'viewer']);
        $this->actingAs($user);
        $token = $user->createToken('test')->plainTextToken;

        $zone = Zone::factory()->create();
        $node = DeviceNode::factory()->create(['zone_id' => $zone->id]);

        $phSensor = Sensor::query()->create([
            'greenhouse_id' => $zone->greenhouse_id,
            'zone_id' => $zone->id,
            'node_id' => $node->id,
            'scope' => 'inside',
            'type' => 'PH',
            'label' => 'ph_sensor',
            'unit' => null,
            'specs' => null,
            'is_active' => true,
        ]);

        $tempSensor = Sensor::query()->create([
            'greenhouse_id' => $zone->greenhouse_id,
            'zone_id' => $zone->id,
            'node_id' => $node->id,
            'scope' => 'inside',
            'type' => 'TEMPERATURE',
            'label' => 'temp_sensor',
            'unit' => '°C',
            'specs' => null,
            'is_active' => true,
        ]);

        TelemetryLast::query()->create([
            'sensor_id' => $phSensor->id,
            'last_value' => 6.5,
            'last_ts' => now()->subMinute(),
            'last_quality' => 'GOOD',
        ]);

        TelemetryLast::query()->create([
            'sensor_id' => $tempSensor->id,
            'last_value' => 23.1,
            'last_ts' => now(),
            'last_quality' => 'GOOD',
        ]);

        $response = $this->withHeader('Authorization', 'Bearer '.$token)
            ->getJson("/api/zones/{$zone->id}/telemetry/last");

        $response->assertOk()
            ->assertJsonPath('status', 'ok')
            ->assertJsonPath('data.ph', 6.5)
            ->assertJsonPath('data.temperature', 23.1);
    }

    public function test_zone_telemetry_last_prefers_air_temperature_and_humidity_channels(): void
    {
        $user = User::factory()->create(['role' => 'viewer']);
        $this->actingAs($user);
        $token = $user->createToken('test')->plainTextToken;

        $zone = Zone::factory()->create();
        $node = DeviceNode::factory()->create(['zone_id' => $zone->id]);

        $solutionTempSensor = Sensor::query()->create([
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

        $airTempSensor = Sensor::query()->create([
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

        $fallbackHumiditySensor = Sensor::query()->create([
            'greenhouse_id' => $zone->greenhouse_id,
            'zone_id' => $zone->id,
            'node_id' => $node->id,
            'scope' => 'inside',
            'type' => 'HUMIDITY',
            'label' => 'humidity_tank',
            'unit' => '%',
            'specs' => null,
            'is_active' => true,
        ]);

        $airHumiditySensor = Sensor::query()->create([
            'greenhouse_id' => $zone->greenhouse_id,
            'zone_id' => $zone->id,
            'node_id' => $node->id,
            'scope' => 'inside',
            'type' => 'HUMIDITY',
            'label' => 'air_rh',
            'unit' => '%',
            'specs' => null,
            'is_active' => true,
        ]);

        TelemetryLast::query()->create([
            'sensor_id' => $solutionTempSensor->id,
            'last_value' => 19.4,
            'last_ts' => now()->subMinute(),
            'last_quality' => 'GOOD',
        ]);

        TelemetryLast::query()->create([
            'sensor_id' => $airTempSensor->id,
            'last_value' => 24.8,
            'last_ts' => now(),
            'last_quality' => 'GOOD',
        ]);

        TelemetryLast::query()->create([
            'sensor_id' => $fallbackHumiditySensor->id,
            'last_value' => 74.0,
            'last_ts' => now()->subMinute(),
            'last_quality' => 'GOOD',
        ]);

        TelemetryLast::query()->create([
            'sensor_id' => $airHumiditySensor->id,
            'last_value' => 61.0,
            'last_ts' => now(),
            'last_quality' => 'GOOD',
        ]);

        $response = $this->withHeader('Authorization', 'Bearer '.$token)
            ->getJson("/api/zones/{$zone->id}/telemetry/last");

        $response->assertOk()
            ->assertJsonPath('status', 'ok')
            ->assertJsonPath('data.temperature', 24.8)
            ->assertJsonPath('data.humidity', 61.0);
    }

    public function test_node_telemetry_history_returns_samples(): void
    {
        $user = User::factory()->create(['role' => 'viewer']);
        $this->actingAs($user);
        $token = $user->createToken('test')->plainTextToken;

        $zone = Zone::factory()->create();
        $node = DeviceNode::factory()->create(['zone_id' => $zone->id]);

        $sensor = Sensor::query()->create([
            'greenhouse_id' => $zone->greenhouse_id,
            'zone_id' => $zone->id,
            'node_id' => $node->id,
            'scope' => 'inside',
            'type' => 'PH',
            'label' => 'ph_sensor',
            'unit' => null,
            'specs' => null,
            'is_active' => true,
        ]);

        TelemetrySample::query()->create([
            'sensor_id' => $sensor->id,
            'ts' => now()->subMinute(),
            'zone_id' => $zone->id,
            'cycle_id' => null,
            'value' => 6.7,
            'quality' => 'GOOD',
            'metadata' => ['metric_type' => 'PH', 'channel' => 'ph_sensor'],
        ]);

        $response = $this->withHeader('Authorization', 'Bearer '.$token)
            ->getJson("/api/nodes/{$node->id}/telemetry/history?metric=PH&channel=ph_sensor");

        $response->assertOk()
            ->assertJsonPath('status', 'ok');

        $first = $response->json('data.0');
        $this->assertSame('PH', $first['metric_type']);
        $this->assertSame('ph_sensor', $first['channel']);
    }

    public function test_telemetry_aggregates_requires_auth(): void
    {
        // Роут использует GET с query параметрами
        $this->getJson('/api/telemetry/aggregates?zone_id=1&metric=ph&period=24h')
            ->assertStatus(401);
    }

    public function test_telemetry_aggregates_validates_zone_access(): void
    {
        $user = User::factory()->create(['role' => 'viewer']);
        $this->actingAs($user);
        $token = $user->createToken('test')->plainTextToken;

        $zone = \App\Models\Zone::factory()->create();

        $response = $this->withHeader('Authorization', 'Bearer '.$token)
            ->getJson("/api/telemetry/aggregates?zone_id={$zone->id}&metric=ph&period=24h");

        // Должен вернуть 200 или пустой массив данных, но не 403
        // (так как ZoneAccessHelper пока разрешает доступ ко всем зонам)
        $response->assertOk()
            ->assertJsonStructure(['status', 'data']);
    }

    public function test_telemetry_aggregates_prefer_air_temperature_channel_over_solution_temperature(): void
    {
        $user = User::factory()->create(['role' => 'viewer']);
        $this->actingAs($user);
        $token = $user->createToken('test')->plainTextToken;

        $zone = Zone::factory()->create();
        $node = DeviceNode::factory()->create(['zone_id' => $zone->id]);

        Sensor::query()->create([
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

        Sensor::query()->create([
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

        $timestamp = now()->startOfHour();

        DB::table('telemetry_agg_1h')->insert([
            [
                'zone_id' => $zone->id,
                'node_id' => $node->id,
                'channel' => 'solution_temp_c',
                'metric_type' => 'TEMPERATURE',
                'value_avg' => 18.0,
                'value_min' => 17.5,
                'value_max' => 18.5,
                'value_median' => 18.0,
                'sample_count' => 3,
                'ts' => $timestamp,
                'created_at' => now(),
            ],
            [
                'zone_id' => $zone->id,
                'node_id' => $node->id,
                'channel' => 'air_temp_c',
                'metric_type' => 'TEMPERATURE',
                'value_avg' => 24.0,
                'value_min' => 23.0,
                'value_max' => 25.0,
                'value_median' => 24.0,
                'sample_count' => 3,
                'ts' => $timestamp,
                'created_at' => now(),
            ],
        ]);

        $response = $this->withHeader('Authorization', 'Bearer '.$token)
            ->getJson("/api/telemetry/aggregates?zone_id={$zone->id}&metric=temperature&period=24h");

        $response->assertOk()
            ->assertJsonPath('status', 'ok')
            ->assertJsonCount(1, 'data')
            ->assertJsonPath('data.0.avg', 24.0)
            ->assertJsonPath('data.0.min', 23.0)
            ->assertJsonPath('data.0.max', 25.0)
            ->assertJsonPath('data.0.median', 24.0);
    }
}
