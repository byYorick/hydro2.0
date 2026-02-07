<?php

namespace Tests\Feature;

use App\Models\SystemLog;
use App\Models\User;
use Carbon\Carbon;
use Laravel\Sanctum\Sanctum;
use Tests\RefreshDatabase;
use Tests\TestCase;

class ServiceLogApiTest extends TestCase
{
    use RefreshDatabase;

    protected function setUp(): void
    {
        parent::setUp();

        $user = User::factory()->create(['role' => 'admin']);
        Sanctum::actingAs($user);
        SystemLog::query()->delete();
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

    public function test_excludes_services_when_requested(): void
    {
        $visible = SystemLog::create([
            'level' => 'info',
            'message' => 'Automation Engine log',
            'context' => ['service' => 'automation-engine'],
            'created_at' => Carbon::now(),
        ]);

        SystemLog::create([
            'level' => 'error',
            'message' => 'History Logger log',
            'context' => ['service' => 'history-logger'],
            'created_at' => Carbon::now(),
        ]);

        $response = $this->getJson('/api/logs/service?exclude_services[]=history-logger');

        $response->assertStatus(200);
        $data = $response->json('data');
        $this->assertCount(1, $data);
        $this->assertEquals($visible->id, $data[0]['id']);
        $this->assertEquals('automation-engine', $data[0]['service']);
    }

    public function test_forbids_access_for_viewer_role(): void
    {
        $viewer = User::factory()->create(['role' => 'viewer']);
        Sanctum::actingAs($viewer);

        $response = $this->getJson('/api/logs/service');

        $response->assertStatus(403);
    }

    public function test_accepts_structured_log_payload(): void
    {
        $timestamp = Carbon::parse('2025-12-20T10:15:30Z');
        $payload = [
            'log' => [
                'timestamp' => $timestamp->toIso8601String(),
                'level' => 'ERROR',
                'logger' => 'scheduler.loop',
                'message' => 'Scheduler tick failed',
                'service' => 'scheduler',
                'trace_id' => 'abc123',
                'exception' => [
                    'type' => 'RuntimeException',
                    'message' => 'boom',
                    'traceback' => ['stack line'],
                ],
            ],
        ];

        $response = $this->postJson('/api/python/logs', $payload);

        $response->assertStatus(200);
        $log = SystemLog::query()->latest('id')->first();
        $this->assertNotNull($log);
        $this->assertEquals('error', $log->level);
        $this->assertEquals('Scheduler tick failed', $log->message);
        $this->assertEquals('scheduler', $log->service);
        $this->assertEquals('scheduler.loop', $log->context['logger'] ?? null);
        $this->assertEquals('abc123', $log->context['trace_id'] ?? null);
        $this->assertEquals('RuntimeException', $log->context['exception']['type'] ?? null);
        $this->assertEquals($timestamp->getTimestamp(), $log->created_at?->getTimestamp());
    }
}
