<?php

namespace Tests\Feature;

use App\Models\SystemLog;
use App\Models\User;
use Carbon\Carbon;
use Tests\RefreshDatabase;
use Laravel\Sanctum\Sanctum;
use Tests\TestCase;

class ServiceLogApiTest extends TestCase
{
    use RefreshDatabase;

    protected function setUp(): void
    {
        parent::setUp();

        $user = User::factory()->create(['role' => 'admin']);
        Sanctum::actingAs($user);
    }

    public function test_returns_logs_with_service_and_level_filters(): void
    {
        SystemLog::create([
            'level' => 'info',
            'message' => 'Should be filtered out',
            'context' => ['service' => 'automation-engine'],
            'created_at' => Carbon::now()->subDay(),
        ]);

        $expected = SystemLog::create([
            'level' => 'error',
            'message' => 'Critical failure',
            'context' => ['service' => 'history-logger', 'node_id' => 42],
            'created_at' => Carbon::now(),
        ]);

        $response = $this->getJson('/api/logs/service?service=history-logger&level=error');

        $response->assertStatus(200);
        $data = $response->json('data');
        $this->assertCount(1, $data);
        $this->assertEquals('history-logger', $data[0]['service']);
        $this->assertEquals('ERROR', $data[0]['level']);
        $this->assertEquals($expected->id, $data[0]['id']);
        $this->assertEquals(1, $response->json('meta.page'));
    }

    public function test_supports_search_and_date_filters(): void
    {
        $todayLog = SystemLog::create([
            'level' => 'warning',
            'message' => 'MQTT disconnect detected',
            'context' => ['service' => 'mqtt-bridge'],
            'created_at' => Carbon::now(),
        ]);

        SystemLog::create([
            'level' => 'warning',
            'message' => 'Old unrelated warning',
            'context' => ['service' => 'mqtt-bridge'],
            'created_at' => Carbon::now()->subDays(3),
        ]);

        $from = Carbon::now()->subDay()->toDateString();
        $response = $this->getJson("/api/logs/service?search=disconnect&from={$from}");

        $response->assertStatus(200);
        $data = $response->json('data');
        $this->assertCount(1, $data);
        $this->assertEquals($todayLog->id, $data[0]['id']);
        $this->assertEquals('mqtt-bridge', $data[0]['service']);
    }

    public function test_forbids_access_for_viewer_role(): void
    {
        $viewer = User::factory()->create(['role' => 'viewer']);
        Sanctum::actingAs($viewer);

        $response = $this->getJson('/api/logs/service');

        $response->assertStatus(403);
    }
}
