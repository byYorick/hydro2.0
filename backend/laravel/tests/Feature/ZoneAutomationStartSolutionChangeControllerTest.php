<?php

namespace Tests\Feature;

use App\Models\User;
use App\Models\Zone;
use Illuminate\Http\Client\Request as HttpRequest;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Http;
use Tests\RefreshDatabase;
use Tests\TestCase;

class ZoneAutomationStartSolutionChangeControllerTest extends TestCase
{
    use RefreshDatabase;

    public function test_start_solution_change_requires_operator_role(): void
    {
        $user = User::factory()->create(['role' => 'viewer']);
        $token = $user->createToken('test')->plainTextToken;
        $zone = Zone::factory()->create();

        $response = $this->actingAs($user)
            ->withHeader('Authorization', 'Bearer '.$token)
            ->postJson("/api/zones/{$zone->id}/start-solution-change", []);

        $response->assertStatus(403);
    }

    public function test_start_solution_change_proxies_payload_to_automation_engine(): void
    {
        config()->set('services.automation_engine.api_url', 'http://automation-engine:9405');
        config()->set('services.automation_engine.scheduler_api_token', 'test-scheduler-token');

        $user = User::factory()->create(['role' => 'operator']);
        $token = $user->createToken('test')->plainTextToken;
        $zone = Zone::factory()->create();

        Http::fake([
            "http://automation-engine:9405/zones/{$zone->id}/start-solution-change" => Http::response([
                'status' => 'ok',
                'data' => [
                    'task_id' => '881',
                    'accepted' => true,
                ],
            ], 200),
        ]);

        $response = $this->actingAs($user)
            ->withHeader('Authorization', 'Bearer '.$token)
            ->postJson("/api/zones/{$zone->id}/start-solution-change", [
                'trigger' => 'operator',
                'idempotency_key' => 'manual-solution-change-881',
            ]);

        $response->assertOk()
            ->assertJsonPath('status', 'ok')
            ->assertJsonPath('data.task_id', '881');

        $intentRow = DB::table('zone_automation_intents')
            ->where('zone_id', $zone->id)
            ->where('idempotency_key', 'manual-solution-change-881')
            ->first();
        $this->assertNotNull($intentRow);
        $this->assertSame('SOLUTION_CHANGE_TICK', $intentRow->intent_type);
        $this->assertSame('pending', $intentRow->status);
        $this->assertSame('solution_change', $intentRow->task_type);

        Http::assertSent(function (HttpRequest $request) use ($zone): bool {
            $body = $request->data();

            return $request->url() === "http://automation-engine:9405/zones/{$zone->id}/start-solution-change"
                && $request->hasHeader('Authorization', 'Bearer test-scheduler-token')
                && ($body['trigger'] ?? null) === 'operator'
                && ($body['idempotency_key'] ?? null) === 'manual-solution-change-881';
        });
    }
}
