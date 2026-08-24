<?php

namespace Tests\Feature;

use App\Models\Alert;
use App\Models\User;
use App\Models\Zone;
use Illuminate\Http\Client\Request as HttpRequest;
use Illuminate\Support\Facades\Http;
use Tests\RefreshDatabase;
use Tests\TestCase;

class ZoneAutomationOperatorUnblockControllerTest extends TestCase
{
    use RefreshDatabase;

    public function test_operator_unblock_requires_authentication(): void
    {
        $zone = Zone::factory()->create();

        $this->postJson("/api/zones/{$zone->id}/operator-unblock", [
            'reason' => 'stuck',
            'confirm' => true,
        ])->assertStatus(401);
    }

    public function test_operator_unblock_requires_operator_role(): void
    {
        $user = User::factory()->create(['role' => 'viewer']);
        $zone = Zone::factory()->create();

        $this->actingAs($user)
            ->withHeader('Authorization', 'Bearer '.$user->createToken('test')->plainTextToken)
            ->postJson("/api/zones/{$zone->id}/operator-unblock", [
                'reason' => 'stuck recirc',
                'confirm' => true,
            ])
            ->assertStatus(403);
    }

    public function test_operator_unblock_requires_reason_and_confirm(): void
    {
        $user = User::factory()->create(['role' => 'operator']);
        $zone = Zone::factory()->create();

        $this->actingAs($user)
            ->withHeader('Authorization', 'Bearer '.$user->createToken('test')->plainTextToken)
            ->postJson("/api/zones/{$zone->id}/operator-unblock", [])
            ->assertStatus(422);
    }

    public function test_operator_unblock_proxies_ae3_and_acks_blocking_alerts(): void
    {
        config()->set('services.automation_engine.scheduler_api_token', 'test-scheduler-token');

        $user = User::factory()->create(['role' => 'operator']);
        $zone = Zone::factory()->create();
        $blocking = Alert::factory()->create([
            'zone_id' => $zone->id,
            'source' => 'biz',
            'code' => 'biz_ae3_task_failed',
            'type' => 'AE3_TASK_FAILED',
            'status' => 'ACTIVE',
            'resolved_at' => null,
        ]);
        $configAlert = Alert::factory()->create([
            'zone_id' => $zone->id,
            'source' => 'biz',
            'code' => 'biz_zone_pid_config_missing',
            'type' => 'PID_MISSING',
            'status' => 'ACTIVE',
            'resolved_at' => null,
        ]);

        Http::fake([
            "http://automation-engine:9405/zones/{$zone->id}/operator-unblock" => Http::response([
                'status' => 'ok',
                'data' => [
                    'zone_id' => $zone->id,
                    'workflow_phase' => 'idle',
                    'failed_task_id' => 77,
                ],
            ], 200),
        ]);

        $response = $this->actingAs($user)
            ->withHeader('Authorization', 'Bearer '.$user->createToken('test')->plainTextToken)
            ->postJson("/api/zones/{$zone->id}/operator-unblock", [
                'reason' => 'hung irrigation',
                'confirm' => true,
            ]);

        $response->assertOk()
            ->assertJsonPath('status', 'ok')
            ->assertJsonPath('data.workflow_phase', 'idle')
            ->assertJsonPath('data.failed_task_id', 77);

        $this->assertContains($blocking->id, $response->json('data.alerts_acked'));
        $this->assertSame('RESOLVED', $blocking->fresh()->status);
        $this->assertNull($configAlert->fresh()->resolved_at);

        Http::assertSent(function (HttpRequest $request) use ($zone): bool {
            return $request->url() === "http://automation-engine:9405/zones/{$zone->id}/operator-unblock"
                && $request->method() === 'POST'
                && $request->hasHeader('X-Trace-Id')
                && $request['reason'] === 'hung irrigation';
        });
    }
}
