<?php

namespace Tests\Feature;

use App\Models\User;
use App\Models\Zone;
use Illuminate\Http\Client\Request as HttpRequest;
use Illuminate\Support\Facades\Http;
use Tests\RefreshDatabase;
use Tests\TestCase;

class ZoneCommandForceIrrigationAe3Test extends TestCase
{
    use RefreshDatabase;

    public function test_force_irrigation_uses_ae3_start_irrigation_path(): void
    {
        config()->set('services.automation_engine.scheduler_api_token', 'test-scheduler-token');

        $user = User::factory()->create(['role' => 'operator']);
        $token = $user->createToken('test')->plainTextToken;
        $zone = Zone::factory()->create();

        Http::fake([
            "http://automation-engine:9405/zones/{$zone->id}/start-irrigation" => Http::response([
                'status' => 'ok',
                'data' => [
                    'task_id' => '991',
                    'accepted' => true,
                ],
            ], 200),
        ]);

        $response = $this->actingAs($user)
            ->withHeader('Authorization', 'Bearer '.$token)
            ->postJson("/api/zones/{$zone->id}/commands", [
                'type' => 'FORCE_IRRIGATION',
                'params' => ['duration_sec' => 90],
            ]);

        $response->assertOk()
            ->assertJsonPath('status', 'ok')
            ->assertJsonPath('data.task_id', '991')
            ->assertJsonPath('data.command_id', 'ae3-task-991');

        Http::assertSent(function (HttpRequest $request) use ($zone): bool {
            $body = $request->data();

            return $request->url() === "http://automation-engine:9405/zones/{$zone->id}/start-irrigation"
                && $request->hasHeader('Authorization', 'Bearer test-scheduler-token')
                && ($body['mode'] ?? null) === 'force'
                && ($body['requested_duration_sec'] ?? null) === 90;
        });
    }
}
