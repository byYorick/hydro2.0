<?php

namespace Tests\Feature;

use App\Models\User;
use App\Models\Zone;
use Illuminate\Support\Facades\Http;
use Tests\RefreshDatabase;
use Tests\TestCase;

class ZoneAutomationControlModeControllerTest extends TestCase
{
    use RefreshDatabase;

    public function test_control_mode_requires_authentication(): void
    {
        $zone = Zone::factory()->create();

        $response = $this->getJson("/api/zones/{$zone->id}/control-mode");
        $response->assertStatus(401);
    }

    public function test_control_mode_get_proxies_payload_from_automation_engine(): void
    {
        $user = User::factory()->create(['role' => 'viewer']);
        $token = $user->createToken('test')->plainTextToken;
        $zone = Zone::factory()->create();

        Http::fake([
            "http://automation-engine:9405/zones/{$zone->id}/control-mode" => Http::response([
                'status' => 'ok',
                'data' => [
                    'zone_id' => $zone->id,
                    'control_mode' => 'manual',
                    'available_modes' => ['auto', 'semi', 'manual'],
                    'allowed_manual_steps' => ['clean_fill_start'],
                ],
            ], 200),
        ]);

        $response = $this->actingAs($user)
            ->withHeader('Authorization', 'Bearer '.$token)
            ->getJson("/api/zones/{$zone->id}/control-mode");

        $response->assertOk()
            ->assertJsonPath('status', 'ok')
            ->assertJsonPath('data.zone_id', $zone->id)
            ->assertJsonPath('data.control_mode', 'manual');
    }

    public function test_control_mode_update_requires_operator_role(): void
    {
        $user = User::factory()->create(['role' => 'viewer']);
        $token = $user->createToken('test')->plainTextToken;
        $zone = Zone::factory()->create();

        $response = $this->actingAs($user)
            ->withHeader('Authorization', 'Bearer '.$token)
            ->postJson("/api/zones/{$zone->id}/control-mode", [
                'control_mode' => 'manual',
            ]);

        $response->assertStatus(403);
    }

    public function test_control_mode_update_proxies_payload_from_automation_engine(): void
    {
        $user = User::factory()->create(['role' => 'operator']);
        $token = $user->createToken('test')->plainTextToken;
        $zone = Zone::factory()->create();

        Http::fake([
            "http://automation-engine:9405/zones/{$zone->id}/control-mode" => Http::response([
                'status' => 'ok',
                'data' => [
                    'zone_id' => $zone->id,
                    'control_mode' => 'semi',
                ],
            ], 200),
        ]);

        $response = $this->actingAs($user)
            ->withHeader('Authorization', 'Bearer '.$token)
            ->postJson("/api/zones/{$zone->id}/control-mode", [
                'control_mode' => 'semi',
            ]);

        $response->assertOk()
            ->assertJsonPath('status', 'ok')
            ->assertJsonPath('data.zone_id', $zone->id)
            ->assertJsonPath('data.control_mode', 'semi');
    }

    public function test_control_mode_get_returns_not_supported_for_missing_upstream_endpoint(): void
    {
        $user = User::factory()->create(['role' => 'viewer']);
        $token = $user->createToken('test')->plainTextToken;
        $zone = Zone::factory()->create();

        Http::fake([
            "http://automation-engine:9405/zones/{$zone->id}/control-mode" => Http::response([
                'status' => 'error',
                'code' => 'NOT_FOUND',
            ], 404),
        ]);

        $response = $this->actingAs($user)
            ->withHeader('Authorization', 'Bearer '.$token)
            ->getJson("/api/zones/{$zone->id}/control-mode");

        $response->assertStatus(501)
            ->assertJsonPath('code', 'UPSTREAM_NOT_SUPPORTED');
    }

    public function test_control_mode_update_propagates_upstream_business_conflict(): void
    {
        $user = User::factory()->create(['role' => 'operator']);
        $token = $user->createToken('test')->plainTextToken;
        $zone = Zone::factory()->create();

        Http::fake([
            "http://automation-engine:9405/zones/{$zone->id}/control-mode" => Http::response([
                'status' => 'error',
                'code' => 'invalid_control_mode',
                'message' => 'invalid control mode',
            ], 422),
        ]);

        $response = $this->actingAs($user)
            ->withHeader('Authorization', 'Bearer '.$token)
            ->postJson("/api/zones/{$zone->id}/control-mode", [
                'control_mode' => 'manual',
            ]);

        $response->assertStatus(422)
            ->assertJsonPath('code', 'invalid_control_mode');
    }
}
