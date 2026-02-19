<?php

namespace Tests\Feature;

use App\Models\User;
use App\Models\Zone;
use Illuminate\Support\Facades\Http;
use Tests\RefreshDatabase;
use Tests\TestCase;

class ZoneAutomationManualResumeControllerTest extends TestCase
{
    use RefreshDatabase;

    public function test_manual_resume_requires_authentication(): void
    {
        $zone = Zone::factory()->create();

        $response = $this->postJson("/api/zones/{$zone->id}/automation/manual-resume");

        $response->assertStatus(401);
    }

    public function test_manual_resume_proxies_payload_from_automation_engine(): void
    {
        $user = User::factory()->create(['role' => 'operator']);
        $token = $user->createToken('test')->plainTextToken;
        $zone = Zone::factory()->create();

        Http::fake([
            "http://automation-engine:9405/zones/{$zone->id}/automation/manual-resume" => Http::response([
                'status' => 'ok',
                'data' => [
                    'zone_id' => $zone->id,
                    'manual_resume' => 'accepted',
                    'task_id' => 'st-manual-1',
                ],
            ], 200),
        ]);

        $response = $this->actingAs($user)
            ->withHeader('Authorization', 'Bearer '.$token)
            ->postJson("/api/zones/{$zone->id}/automation/manual-resume", [
                'task_id' => 'st-manual-1',
            ]);

        $response->assertOk()
            ->assertJsonPath('status', 'ok')
            ->assertJsonPath('data.zone_id', $zone->id)
            ->assertJsonPath('data.manual_resume', 'accepted')
            ->assertJsonPath('data.task_id', 'st-manual-1');
    }

    public function test_manual_resume_returns_not_supported_when_upstream_endpoint_missing(): void
    {
        $user = User::factory()->create(['role' => 'operator']);
        $token = $user->createToken('test')->plainTextToken;
        $zone = Zone::factory()->create();

        Http::fake([
            "http://automation-engine:9405/zones/{$zone->id}/automation/manual-resume" => Http::response([
                'status' => 'error',
                'code' => 'NOT_FOUND',
                'message' => 'not found',
            ], 404),
        ]);

        $response = $this->actingAs($user)
            ->withHeader('Authorization', 'Bearer '.$token)
            ->postJson("/api/zones/{$zone->id}/automation/manual-resume", [
                'task_id' => 'st-manual-2',
            ]);

        $response->assertStatus(501)
            ->assertJsonPath('status', 'error')
            ->assertJsonPath('code', 'UPSTREAM_NOT_SUPPORTED');
    }

    public function test_manual_resume_forbidden_for_viewer_role(): void
    {
        $user = User::factory()->create(['role' => 'viewer']);
        $token = $user->createToken('test')->plainTextToken;
        $zone = Zone::factory()->create();

        $response = $this->actingAs($user)
            ->withHeader('Authorization', 'Bearer '.$token)
            ->postJson("/api/zones/{$zone->id}/automation/manual-resume", [
                'task_id' => 'st-manual-3',
            ]);

        $response->assertStatus(403);
    }
}
