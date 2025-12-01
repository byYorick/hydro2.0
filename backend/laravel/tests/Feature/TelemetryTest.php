<?php

namespace Tests\Feature;

use App\Models\User;
use Illuminate\Foundation\Testing\RefreshDatabase;
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


