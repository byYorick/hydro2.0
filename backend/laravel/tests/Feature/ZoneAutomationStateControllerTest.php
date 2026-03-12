<?php

namespace Tests\Feature;

use App\Models\User;
use App\Models\Zone;
use Illuminate\Support\Facades\Cache;
use Illuminate\Support\Facades\Http;
use Tests\RefreshDatabase;
use Tests\TestCase;

class ZoneAutomationStateControllerTest extends TestCase
{
    use RefreshDatabase;

    public function test_automation_state_requires_authentication(): void
    {
        $zone = Zone::factory()->create();

        $response = $this->getJson("/api/zones/{$zone->id}/state");

        $response->assertStatus(401);
    }

    public function test_automation_state_proxies_payload_from_automation_engine(): void
    {
        Cache::flush();

        $user = User::factory()->create(['role' => 'viewer']);
        $token = $user->createToken('test')->plainTextToken;
        $zone = Zone::factory()->create();

        Http::fake([
            "http://automation-engine:9405/zones/{$zone->id}/state" => Http::response([
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
            ->getJson("/api/zones/{$zone->id}/state");

        $response->assertOk()
            ->assertJsonPath('zone_id', $zone->id)
            ->assertJsonPath('state', 'TANK_FILLING')
            ->assertJsonPath('system_config.tanks_count', 2)
            ->assertJsonPath('active_processes.pump_in', true)
            ->assertJsonPath('state_meta.source', 'live')
            ->assertJsonPath('state_meta.is_stale', false);
    }

    public function test_automation_state_returns_upstream_unavailable_on_request_exception(): void
    {
        Cache::flush();

        $user = User::factory()->create(['role' => 'viewer']);
        $token = $user->createToken('test')->plainTextToken;
        $zone = Zone::factory()->create();

        Http::fake([
            "http://automation-engine:9405/zones/{$zone->id}/state" => Http::response([
                'status' => 'error',
                'message' => 'temporary degradation',
            ], 500),
        ]);

        $response = $this->actingAs($user)
            ->withHeader('Authorization', 'Bearer '.$token)
            ->getJson("/api/zones/{$zone->id}/state");

        $response->assertStatus(503)
            ->assertJsonPath('status', 'error')
            ->assertJsonPath('code', 'UPSTREAM_UNAVAILABLE');
    }

    public function test_automation_state_returns_cached_snapshot_when_upstream_is_temporarily_unavailable(): void
    {
        Cache::flush();

        $user = User::factory()->create(['role' => 'viewer']);
        $token = $user->createToken('test')->plainTextToken;
        $zone = Zone::factory()->create();

        Http::fake([
            "http://automation-engine:9405/zones/{$zone->id}/state" => Http::response([
                'zone_id' => $zone->id,
                'state' => 'TANK_RECIRC',
                'state_label' => 'Рециркуляция бака',
                'state_details' => [
                    'started_at' => now()->subSeconds(10)->toIso8601String(),
                    'elapsed_sec' => 10,
                    'progress_percent' => 42,
                ],
                'system_config' => [
                    'tanks_count' => 2,
                    'system_type' => 'drip',
                    'clean_tank_capacity_l' => 50,
                    'nutrient_tank_capacity_l' => 100,
                ],
                'current_levels' => [
                    'clean_tank_level_percent' => 85,
                    'nutrient_tank_level_percent' => 70,
                    'ph' => 5.9,
                    'ec' => 1.5,
                ],
                'active_processes' => [
                    'pump_in' => false,
                    'circulation_pump' => true,
                    'ph_correction' => true,
                    'ec_correction' => true,
                ],
                'timeline' => [],
                'next_state' => 'READY',
                'estimated_completion_sec' => 120,
            ], 200),
        ]);

        $this->actingAs($user)
            ->withHeader('Authorization', 'Bearer '.$token)
            ->getJson("/api/zones/{$zone->id}/state")
            ->assertOk()
            ->assertJsonPath('state_meta.source', 'live')
            ->assertJsonPath('state_meta.is_stale', false);

        Http::fake([
            "http://automation-engine:9405/zones/{$zone->id}/state" => function () {
                throw new \RuntimeException('upstream_down');
            },
        ]);

        $response = $this->actingAs($user)
            ->withHeader('Authorization', 'Bearer '.$token)
            ->getJson("/api/zones/{$zone->id}/state");

        $response->assertOk()
            ->assertJsonPath('zone_id', $zone->id)
            ->assertJsonPath('state', 'TANK_RECIRC')
            ->assertJsonPath('state_meta.source', 'cache')
            ->assertJsonPath('state_meta.is_stale', true);
    }

    public function test_automation_state_falls_back_to_control_mode_when_state_endpoint_is_missing(): void
    {
        Cache::flush();

        $user = User::factory()->create(['role' => 'viewer']);
        $token = $user->createToken('test')->plainTextToken;
        $zone = Zone::factory()->create();

        Http::fake([
            "http://automation-engine:9405/zones/{$zone->id}/state" => Http::response([
                'detail' => 'Not Found',
            ], 404),
            "http://automation-engine:9405/zones/{$zone->id}/control-mode" => Http::response([
                'data' => [
                    'zone_id' => $zone->id,
                    'control_mode' => 'semi',
                    'workflow_phase' => 'tank_recirc',
                    'current_stage' => 'prepare_recirculation_check',
                    'allowed_manual_steps' => ['prepare_recirculation_stop_to_ready'],
                ],
            ], 200),
        ]);

        $response = $this->actingAs($user)
            ->withHeader('Authorization', 'Bearer '.$token)
            ->getJson("/api/zones/{$zone->id}/state");

        $response->assertOk()
            ->assertJsonPath('zone_id', $zone->id)
            ->assertJsonPath('state', 'TANK_RECIRC')
            ->assertJsonPath('state_label', 'Рециркуляция раствора')
            ->assertJsonPath('control_mode', 'semi')
            ->assertJsonPath('workflow_phase', 'tank_recirc')
            ->assertJsonPath('current_stage', 'prepare_recirculation_check')
            ->assertJsonPath('allowed_manual_steps.0', 'prepare_recirculation_stop_to_ready')
            ->assertJsonPath('compatibility.source', 'ae3_control_mode_fallback')
            ->assertJsonPath('state_meta.source', 'live')
            ->assertJsonPath('state_meta.is_stale', false);
    }
}
