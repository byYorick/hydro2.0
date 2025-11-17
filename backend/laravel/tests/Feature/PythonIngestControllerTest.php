<?php

namespace Tests\Feature;

use App\Models\User;
use App\Models\Zone;
use App\Models\DeviceNode;
use App\Models\TelemetrySample;
use App\Models\TelemetryLast;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Illuminate\Support\Facades\Http;
use Illuminate\Support\Facades\Config;
use Tests\TestCase;

class PythonIngestControllerTest extends TestCase
{
    use RefreshDatabase;

    private function token(): string
    {
        $user = User::factory()->create();
        return $user->createToken('test')->plainTextToken;
    }

    public function test_telemetry_endpoint_requires_auth(): void
    {
        $this->postJson('/api/python/ingest/telemetry', [
            'zone_id' => 1,
            'metric_type' => 'ph',
            'value' => 6.5,
        ])->assertStatus(401);
    }

    public function test_telemetry_endpoint_proxies_to_history_logger(): void
    {
        Http::fake([
            'history-logger:9300/ingest/telemetry' => Http::response([
                'status' => 'ok',
                'count' => 1,
            ], 200),
        ]);

        Config::set('services.history_logger.url', 'http://history-logger:9300');
        Config::set('services.python_bridge.ingest_token', 'test-token');

        $zone = Zone::factory()->create();
        $node = DeviceNode::factory()->create(['zone_id' => $zone->id]);

        $token = $this->token();
        
        $response = $this->withHeader('Authorization', 'Bearer test-token')
            ->postJson('/api/python/ingest/telemetry', [
                'zone_id' => $zone->id,
                'node_id' => $node->id,
                'metric_type' => 'ph',
                'value' => 6.5,
                'channel' => 'ph_sensor',
            ]);

        $response->assertOk()
            ->assertJson(['status' => 'ok']);

        // Проверяем, что запрос был отправлен в history-logger
        Http::assertSent(function ($request) use ($zone, $node) {
            return $request->url() === 'http://history-logger:9300/ingest/telemetry'
                && $request->method() === 'POST'
                && isset($request->data()['samples'])
                && count($request->data()['samples']) === 1
                && $request->data()['samples'][0]['node_uid'] === $node->uid
                && $request->data()['samples'][0]['zone_id'] === $zone->id
                && $request->data()['samples'][0]['metric_type'] === 'ph'
                && $request->data()['samples'][0]['value'] === 6.5;
        });
    }

    public function test_telemetry_endpoint_does_not_write_to_database(): void
    {
        Http::fake([
            'history-logger:9300/ingest/telemetry' => Http::response([
                'status' => 'ok',
                'count' => 1,
            ], 200),
        ]);

        Config::set('services.history_logger.url', 'http://history-logger:9300');
        Config::set('services.python_bridge.ingest_token', 'test-token');

        $zone = Zone::factory()->create();
        $node = DeviceNode::factory()->create(['zone_id' => $zone->id]);

        $samplesBefore = TelemetrySample::count();
        $lastBefore = TelemetryLast::count();

        $this->withHeader('Authorization', 'Bearer test-token')
            ->postJson('/api/python/ingest/telemetry', [
                'zone_id' => $zone->id,
                'node_id' => $node->id,
                'metric_type' => 'ph',
                'value' => 6.5,
            ]);

        // Проверяем, что данные НЕ записаны напрямую в БД Laravel
        $this->assertEquals($samplesBefore, TelemetrySample::count());
        $this->assertEquals($lastBefore, TelemetryLast::count());
    }

    public function test_telemetry_endpoint_handles_history_logger_error(): void
    {
        Http::fake([
            'history-logger:9300/ingest/telemetry' => Http::response([
                'status' => 'error',
                'message' => 'Internal error',
            ], 500),
        ]);

        Config::set('services.history_logger.url', 'http://history-logger:9300');
        Config::set('services.python_bridge.ingest_token', 'test-token');

        $zone = Zone::factory()->create();
        $node = DeviceNode::factory()->create(['zone_id' => $zone->id]);

        $response = $this->withHeader('Authorization', 'Bearer test-token')
            ->postJson('/api/python/ingest/telemetry', [
                'zone_id' => $zone->id,
                'node_id' => $node->id,
                'metric_type' => 'ph',
                'value' => 6.5,
            ]);

        $response->assertStatus(500)
            ->assertJson(['status' => 'error']);
    }

    public function test_telemetry_endpoint_validation(): void
    {
        Config::set('services.python_bridge.ingest_token', 'test-token');

        $response = $this->withHeader('Authorization', 'Bearer test-token')
            ->postJson('/api/python/ingest/telemetry', [
                // Отсутствует zone_id
                'metric_type' => 'ph',
                'value' => 6.5,
            ]);

        $response->assertStatus(422); // Validation error
    }

    public function test_command_ack_endpoint_does_not_update_status(): void
    {
        Config::set('services.python_bridge.ingest_token', 'test-token');

        // Создаём команду напрямую
        $command = \App\Models\Command::create([
            'cmd_id' => 'cmd-test-123',
            'status' => 'pending',
            'cmd' => 'test_command',
        ]);

        $response = $this->withHeader('Authorization', 'Bearer test-token')
            ->postJson('/api/python/commands/ack', [
                'cmd_id' => 'cmd-test-123',
                'status' => 'completed',
            ]);

        $response->assertOk()
            ->assertJson(['status' => 'ok']);

        // Проверяем, что статус команды НЕ обновлён
        $command->refresh();
        $this->assertEquals('pending', $command->status);
        // Laravel больше не обновляет статусы команд
    }

    public function test_command_ack_endpoint_requires_auth(): void
    {
        $this->postJson('/api/python/commands/ack', [
            'cmd_id' => 'cmd-test-123',
            'status' => 'completed',
        ])->assertStatus(401);
    }
}

