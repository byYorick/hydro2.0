<?php

namespace Tests\Feature;

use App\Models\User;
use App\Models\ZoneSimulation;
use Illuminate\Support\Carbon;
use Illuminate\Support\Facades\DB;
use Tests\RefreshDatabase;
use Tests\TestCase;

class SimulationEventsTest extends TestCase
{
    use RefreshDatabase;

    public function test_simulation_events_requires_authentication(): void
    {
        $simulation = ZoneSimulation::factory()->create();

        $response = $this->getJson("/api/simulations/{$simulation->id}/events");

        $response->assertStatus(401);
    }

    public function test_simulation_events_returns_filtered_list(): void
    {
        $user = User::factory()->create(['role' => 'operator']);
        $simulation = ZoneSimulation::factory()->create();

        DB::table('simulation_events')->insert([
            'simulation_id' => $simulation->id,
            'zone_id' => $simulation->zone_id,
            'service' => 'digital-twin',
            'stage' => 'live_init',
            'status' => 'running',
            'level' => 'info',
            'message' => 'init',
            'payload' => json_encode(['step' => 1], JSON_UNESCAPED_UNICODE),
            'occurred_at' => Carbon::now()->subMinutes(2),
            'created_at' => Carbon::now()->subMinutes(2),
        ]);
        DB::table('simulation_events')->insert([
            'simulation_id' => $simulation->id,
            'zone_id' => $simulation->zone_id,
            'service' => 'node-sim-manager',
            'stage' => 'session_start',
            'status' => 'failed',
            'level' => 'error',
            'message' => 'node sim error',
            'payload' => json_encode(['error' => 'boom'], JSON_UNESCAPED_UNICODE),
            'occurred_at' => Carbon::now()->subMinute(),
            'created_at' => Carbon::now()->subMinute(),
        ]);

        $response = $this->actingAs($user)->getJson("/api/simulations/{$simulation->id}/events?level=error");

        $response->assertStatus(200);
        $response->assertJsonPath('status', 'ok');
        $response->assertJsonCount(1, 'data');
        $response->assertJsonPath('data.0.service', 'node-sim-manager');
        $response->assertJsonPath('data.0.level', 'error');
    }

    public function test_simulation_events_supports_after_id(): void
    {
        $user = User::factory()->create(['role' => 'operator']);
        $simulation = ZoneSimulation::factory()->create();

        $firstId = DB::table('simulation_events')->insertGetId([
            'simulation_id' => $simulation->id,
            'zone_id' => $simulation->zone_id,
            'service' => 'laravel',
            'stage' => 'job',
            'status' => 'running',
            'level' => 'info',
            'message' => 'started',
            'payload' => json_encode(['job_id' => 'sim-1'], JSON_UNESCAPED_UNICODE),
            'occurred_at' => Carbon::now()->subMinutes(5),
            'created_at' => Carbon::now()->subMinutes(5),
        ]);
        $secondId = DB::table('simulation_events')->insertGetId([
            'simulation_id' => $simulation->id,
            'zone_id' => $simulation->zone_id,
            'service' => 'digital-twin',
            'stage' => 'live_complete',
            'status' => 'completed',
            'level' => 'info',
            'message' => 'done',
            'payload' => json_encode(['result' => 'ok'], JSON_UNESCAPED_UNICODE),
            'occurred_at' => Carbon::now()->subMinutes(4),
            'created_at' => Carbon::now()->subMinutes(4),
        ]);

        $response = $this->actingAs($user)->getJson(
            "/api/simulations/{$simulation->id}/events?after_id={$firstId}&order=asc"
        );

        $response->assertStatus(200);
        $response->assertJsonPath('status', 'ok');
        $response->assertJsonCount(1, 'data');
        $response->assertJsonPath('data.0.id', $secondId);
    }
}
