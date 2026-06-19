<?php

namespace Tests\Feature;

use App\Models\User;
use App\Models\Zone;
use Illuminate\Http\Client\Request as HttpRequest;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Http;
use Tests\RefreshDatabase;
use Tests\TestCase;

class ZoneAutomationStartCycleControllerTest extends TestCase
{
    use RefreshDatabase;

    public function test_start_cycle_requires_operator_role(): void
    {
        $user = User::factory()->create(['role' => 'viewer']);
        $token = $user->createToken('test')->plainTextToken;
        $zone = Zone::factory()->create();

        $response = $this->actingAs($user)
            ->withHeader('Authorization', 'Bearer '.$token)
            ->postJson("/api/zones/{$zone->id}/start-cycle", []);

        $response->assertStatus(403);
    }

    public function test_start_cycle_proxies_payload_to_automation_engine(): void
    {
        config()->set('services.automation_engine.api_url', 'http://automation-engine:9405');
        config()->set('services.automation_engine.scheduler_api_token', 'test-scheduler-token');

        $user = User::factory()->create(['role' => 'operator']);
        $token = $user->createToken('test')->plainTextToken;
        $zone = Zone::factory()->create();

        Http::fake([
            "http://automation-engine:9405/zones/{$zone->id}/start-cycle" => Http::response([
                'status' => 'ok',
                'data' => [
                    'task_id' => '888',
                    'accepted' => true,
                ],
            ], 200),
        ]);

        $response = $this->actingAs($user)
            ->withHeader('Authorization', 'Bearer '.$token)
            ->postJson("/api/zones/{$zone->id}/start-cycle", [
                'source' => 'frontend',
                'idempotency_key' => 'manual-diagnostics-888',
            ]);

        $response->assertOk()
            ->assertJsonPath('status', 'ok')
            ->assertJsonPath('data.task_id', '888');

        $intentRow = DB::table('zone_automation_intents')
            ->where('zone_id', $zone->id)
            ->where('idempotency_key', 'manual-diagnostics-888')
            ->first();
        $this->assertNotNull($intentRow);
        $this->assertSame('DIAGNOSTICS_TICK', $intentRow->intent_type);
        $this->assertSame('pending', $intentRow->status);
        $this->assertSame('frontend', $intentRow->intent_source);
        $this->assertSame('cycle_start', $intentRow->task_type);
        $this->assertSame('two_tank_drip_substrate_trays', $intentRow->topology);

        Http::assertSent(function (HttpRequest $request) use ($zone): bool {
            $body = $request->data();

            return $request->url() === "http://automation-engine:9405/zones/{$zone->id}/start-cycle"
                && $request->hasHeader('Authorization', 'Bearer test-scheduler-token')
                && $request->hasHeader('X-Trace-Id')
                && ($body['source'] ?? null) === 'frontend'
                && ($body['idempotency_key'] ?? null) === 'manual-diagnostics-888';
        });
    }
}
