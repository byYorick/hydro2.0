<?php

namespace Tests\Feature;

use App\Models\User;
use App\Models\Zone;
use Illuminate\Http\Client\Request as HttpRequest;
use Illuminate\Support\Facades\Http;
use Tests\RefreshDatabase;
use Tests\TestCase;

class ZoneAutomationStartIrrigationControllerTest extends TestCase
{
    use RefreshDatabase;

    public function test_start_irrigation_requires_operator_role(): void
    {
        $user = User::factory()->create(['role' => 'viewer']);
        $token = $user->createToken('test')->plainTextToken;
        $zone = Zone::factory()->create();

        $response = $this->actingAs($user)
            ->withHeader('Authorization', 'Bearer '.$token)
            ->postJson("/api/zones/{$zone->id}/start-irrigation", [
                'mode' => 'normal',
            ]);

        $response->assertStatus(403);
    }

    public function test_start_irrigation_proxies_payload_to_automation_engine(): void
    {
        config()->set('services.automation_engine.scheduler_api_token', 'test-scheduler-token');

        $user = User::factory()->create(['role' => 'operator']);
        $token = $user->createToken('test')->plainTextToken;
        $zone = Zone::factory()->create();

        Http::fake([
            "http://automation-engine:9405/zones/{$zone->id}/start-irrigation" => Http::response([
                'status' => 'ok',
                'data' => [
                    'task_id' => '777',
                    'accepted' => true,
                ],
            ], 200),
        ]);

        $response = $this->actingAs($user)
            ->withHeader('Authorization', 'Bearer '.$token)
            ->postJson("/api/zones/{$zone->id}/start-irrigation", [
                'mode' => 'force',
                'requested_duration_sec' => 120,
                'idempotency_key' => 'manual-force-irrigation-777',
            ]);

        $response->assertOk()
            ->assertJsonPath('status', 'ok')
            ->assertJsonPath('data.task_id', '777');

        Http::assertSent(function (HttpRequest $request) use ($zone): bool {
            $body = $request->data();

            return $request->url() === "http://automation-engine:9405/zones/{$zone->id}/start-irrigation"
                && $request->hasHeader('Authorization', 'Bearer test-scheduler-token')
                && $request->hasHeader('X-Trace-Id')
                && ($body['mode'] ?? null) === 'force'
                && ($body['requested_duration_sec'] ?? null) === 120;
        });
    }
}
