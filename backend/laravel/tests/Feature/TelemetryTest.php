<?php

namespace Tests\Feature;

use App\Models\DeviceNode;
use App\Models\Sensor;
use App\Models\TelemetryLast;
use App\Models\TelemetrySample;
use App\Models\User;
use App\Models\Zone;
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
}
