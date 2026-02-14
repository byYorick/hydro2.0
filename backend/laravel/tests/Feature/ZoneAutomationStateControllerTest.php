<?php

namespace Tests\Feature;

use App\Models\User;
use App\Models\Zone;
use Illuminate\Support\Facades\Http;
use Tests\RefreshDatabase;
use Tests\TestCase;

class ZoneAutomationStateControllerTest extends TestCase
{
    use RefreshDatabase;

    public function test_automation_state_requires_authentication(): void
    {
        $zone = Zone::factory()->create();

        $response = $this->getJson("/api/zones/{$zone->id}/automation-state");

        $response->assertStatus(401);
    }

    public function test_automation_state_proxies_payload_from_automation_engine(): void
    {
        $user = User::factory()->create(['role' => 'viewer']);
        $token = $user->createToken('test')->plainTextToken;
        $zone = Zone::factory()->create();

        Http::fake([
            "http://automation-engine:9405/zones/{$zone->id}/automation-state" => Http::response([
                'zone_id' => $zone->id,
                'state' => 'TANK_FILLING',
                'state_label' => 'Набор бака с раствором',
                'state_details' => [
                    'started_at' => now()->subSeconds(45)->toIso8601String(),
                    'elapsed_sec' => 45,
                    'progress_percent' => 30,
                ],
                'system_config' => [
                    'tanks_count' => 2,
                    'system_type' => 'drip',
                    'clean_tank_capacity_l' => 50,
                    'nutrient_tank_capacity_l' => 100,
                ],
                'current_levels' => [
                    'clean_tank_level_percent' => 70,
                    'nutrient_tank_level_percent' => 45,
                    'ph' => 5.9,
                    'ec' => 1.4,
                ],
                'active_processes' => [
                    'pump_in' => true,
                    'circulation_pump' => false,
                    'ph_correction' => true,
                    'ec_correction' => true,
                ],
                'timeline' => [],
                'next_state' => 'TANK_RECIRC',
                'estimated_completion_sec' => 120,
            ], 200),
        ]);

        $response = $this->actingAs($user)
            ->withHeader('Authorization', 'Bearer '.$token)
            ->getJson("/api/zones/{$zone->id}/automation-state");

        $response->assertOk()
            ->assertJsonPath('zone_id', $zone->id)
            ->assertJsonPath('state', 'TANK_FILLING')
            ->assertJsonPath('system_config.tanks_count', 2)
            ->assertJsonPath('active_processes.pump_in', true);
    }

    public function test_automation_state_returns_upstream_unavailable_on_request_exception(): void
    {
        $user = User::factory()->create(['role' => 'viewer']);
        $token = $user->createToken('test')->plainTextToken;
        $zone = Zone::factory()->create();

        Http::fake([
            "http://automation-engine:9405/zones/{$zone->id}/automation-state" => Http::response([
                'status' => 'error',
                'message' => 'temporary degradation',
            ], 500),
        ]);

        $response = $this->actingAs($user)
            ->withHeader('Authorization', 'Bearer '.$token)
            ->getJson("/api/zones/{$zone->id}/automation-state");

        $response->assertStatus(503)
            ->assertJsonPath('status', 'error')
            ->assertJsonPath('code', 'UPSTREAM_UNAVAILABLE');
    }
}
