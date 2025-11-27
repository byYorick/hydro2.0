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
        $user = User::factory()->create();
        $this->actingAs($user);
        $token = $user->createToken('test')->plainTextToken;

        $resp = $this->withHeader('Authorization', 'Bearer '.$token)
            ->getJson('/api/zones/1/telemetry/history');
        $resp->assertStatus(422);
    }
}


