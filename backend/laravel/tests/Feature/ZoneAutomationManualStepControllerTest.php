<?php

namespace Tests\Feature;

use App\Models\User;
use App\Models\Zone;
use Illuminate\Support\Facades\Http;
use Tests\RefreshDatabase;
use Tests\TestCase;

class ZoneAutomationManualStepControllerTest extends TestCase
{
    use RefreshDatabase;

    public function test_manual_step_requires_authentication(): void
    {
        $zone = Zone::factory()->create();

        $response = $this->postJson("/api/zones/{$zone->id}/automation/manual-step");

        $response->assertStatus(401);
    }

    public function test_manual_step_requires_operator_role(): void
    {
        $user = User::factory()->create(['role' => 'viewer']);
        $token = $user->createToken('test')->plainTextToken;
        $zone = Zone::factory()->create();

        $response = $this->actingAs($user)
            ->withHeader('Authorization', 'Bearer '.$token)
            ->postJson("/api/zones/{$zone->id}/automation/manual-step", [
                'manual_step' => 'clean_fill_start',
            ]);

        $response->assertStatus(403);
    }

    public function test_manual_step_proxies_payload_from_automation_engine(): void
    {
        $user = User::factory()->create(['role' => 'operator']);
        $token = $user->createToken('test')->plainTextToken;
        $zone = Zone::factory()->create();

        Http::fake([
            "http://automation-engine:9405/zones/{$zone->id}/automation/manual-step" => Http::response([
                'status' => 'ok',
                'data' => [
                    'zone_id' => $zone->id,
                    'task_id' => 'st-manual-step-1',
                    'manual_step' => 'clean_fill_start',
                    'control_mode' => 'manual',
                ],
            ], 200),
        ]);

        $response = $this->actingAs($user)
            ->withHeader('Authorization', 'Bearer '.$token)
            ->postJson("/api/zones/{$zone->id}/automation/manual-step", [
                'manual_step' => 'clean_fill_start',
            ]);

        $response->assertOk()
            ->assertJsonPath('status', 'ok')
            ->assertJsonPath('data.zone_id', $zone->id)
            ->assertJsonPath('data.task_id', 'st-manual-step-1')
            ->assertJsonPath('data.manual_step', 'clean_fill_start');
    }

    public function test_manual_step_validates_step_name(): void
    {
        $user = User::factory()->create(['role' => 'operator']);
        $token = $user->createToken('test')->plainTextToken;
        $zone = Zone::factory()->create();

        $response = $this->actingAs($user)
            ->withHeader('Authorization', 'Bearer '.$token)
            ->postJson("/api/zones/{$zone->id}/automation/manual-step", [
                'manual_step' => 'invalid_step',
            ]);

        $response->assertStatus(422);
    }

    public function test_manual_step_propagates_upstream_business_conflict(): void
    {
        $user = User::factory()->create(['role' => 'operator']);
        $token = $user->createToken('test')->plainTextToken;
        $zone = Zone::factory()->create();

        Http::fake([
            "http://automation-engine:9405/zones/{$zone->id}/automation/manual-step" => Http::response([
                'status' => 'error',
                'code' => 'manual_step_forbidden_in_auto_mode',
                'message' => 'manual step disabled in auto mode',
            ], 409),
        ]);

        $response = $this->actingAs($user)
            ->withHeader('Authorization', 'Bearer '.$token)
            ->postJson("/api/zones/{$zone->id}/automation/manual-step", [
                'manual_step' => 'clean_fill_start',
            ]);

        $response->assertStatus(409)
            ->assertJsonPath('code', 'manual_step_forbidden_in_auto_mode');
    }
}
