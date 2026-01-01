<?php

namespace Tests\Feature;

use App\Models\User;
use App\Models\Zone;
use App\Models\DeviceNode;
use App\Models\Command;
use App\Models\TelemetrySample;
use App\Models\TelemetryLast;
use Tests\RefreshDatabase;
use Illuminate\Support\Facades\Http;
use Illuminate\Support\Facades\Config;
use Tests\TestCase;

class PythonIngestControllerTest extends TestCase
{
    use RefreshDatabase;

    private function token(string $role = 'operator'): string
    {
        $user = User::factory()->create(['role' => $role]);
        $this->actingAs($user);

        return $user->createToken('test')->plainTextToken;
    }

    public function test_telemetry_endpoint_requires_auth(): void
    {
        $this->postJson('/api/python/ingest/telemetry', [
            'zone_id' => 1,
            'metric_type' => 'PH',
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
                'metric_type' => 'PH',
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
                && $request->data()['samples'][0]['metric_type'] === 'PH'
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
                'metric_type' => 'PH',
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
                'metric_type' => 'PH',
                'value' => 6.5,
            ]);

        $response->assertStatus(500)
            ->assertJson(['status' => 'error']);
    }

    public function test_telemetry_endpoint_validation(): void
    {
        Config::set('services.python_bridge.ingest_token', 'test-token');
        Config::set('services.python_bridge.token', 'test-token');

        // Тест: отсутствует zone_id
        $response = $this->withHeader('Authorization', 'Bearer test-token')
            ->postJson('/api/python/ingest/telemetry', [
                'metric_type' => 'PH',
                'value' => 6.5,
            ]);
        $response->assertStatus(422); // Validation error

        // Тест: zone_id не существует
        $response = $this->withHeader('Authorization', 'Bearer test-token')
            ->postJson('/api/python/ingest/telemetry', [
                'zone_id' => 99999, // Несуществующий zone_id
                'metric_type' => 'PH',
                'value' => 6.5,
            ]);
        $response->assertStatus(422); // Validation error

        // Тест: node_id не существует
        $zone = Zone::factory()->create();
        $response = $this->withHeader('Authorization', 'Bearer test-token')
            ->postJson('/api/python/ingest/telemetry', [
                'zone_id' => $zone->id,
                'node_id' => 99999, // Несуществующий node_id
                'metric_type' => 'PH',
                'value' => 6.5,
            ]);
        $response->assertStatus(422); // Validation error (exists:nodes,id)

        // Тест: node_id не привязан к zone_id
        $zone1 = Zone::factory()->create();
        $zone2 = Zone::factory()->create();
        $node = DeviceNode::factory()->create(['zone_id' => $zone1->id]);
        
        $response = $this->withHeader('Authorization', 'Bearer test-token')
            ->postJson('/api/python/ingest/telemetry', [
                'zone_id' => $zone2->id, // Другая зона
                'node_id' => $node->id, // Нода привязана к zone1
                'metric_type' => 'PH',
                'value' => 6.5,
            ]);
        $response->assertStatus(422) // Validation error
            ->assertJson(['status' => 'error', 'message' => 'Node is not assigned to the specified zone']);
    }

    public function test_telemetry_endpoint_validates_node_belongs_to_zone(): void
    {
        Config::set('services.python_bridge.ingest_token', 'test-token');
        Config::set('services.python_bridge.token', 'test-token');

        $zone1 = Zone::factory()->create();
        $zone2 = Zone::factory()->create();
        $node = DeviceNode::factory()->create(['zone_id' => $zone1->id]);

        // Попытка отправить телеметрию с node_id из zone1, но указать zone_id = zone2
        $response = $this->withHeader('Authorization', 'Bearer test-token')
            ->postJson('/api/python/ingest/telemetry', [
                'zone_id' => $zone2->id, // Другая зона
                'node_id' => $node->id, // Нода из zone1
                'metric_type' => 'PH',
                'value' => 6.5,
            ]);

        $response->assertStatus(422)
            ->assertJson(['status' => 'error', 'message' => 'Node is not assigned to the specified zone']);
    }

    public function test_telemetry_endpoint_allows_zone_without_node(): void
    {
        Http::fake([
            'history-logger:9300/ingest/telemetry' => Http::response([
                'status' => 'ok',
                'count' => 1,
            ], 200),
        ]);

        Config::set('services.history_logger.url', 'http://history-logger:9300');
        Config::set('services.python_bridge.ingest_token', 'test-token');
        Config::set('services.python_bridge.token', 'test-token');

        $zone = Zone::factory()->create();

        // Телеметрия без node_id должна быть разрешена
        $response = $this->withHeader('Authorization', 'Bearer test-token')
            ->postJson('/api/python/ingest/telemetry', [
                'zone_id' => $zone->id,
                'metric_type' => 'PH',
                'value' => 6.5,
            ]);

        $response->assertOk()
            ->assertJson(['status' => 'ok']);
    }

    public function test_command_ack_endpoint_does_not_update_status(): void
    {
        Config::set('services.python_bridge.ingest_token', 'test-token');

        // Создаём команду напрямую
        $command = \App\Models\Command::create([
            'cmd_id' => 'cmd-test-123',
            'status' => Command::STATUS_QUEUED,
            'cmd' => 'test_command',
        ]);

        $response = $this->withHeader('Authorization', 'Bearer test-token')
            ->postJson('/api/python/commands/ack', [
                'cmd_id' => 'cmd-test-123',
                'status' => 'completed',
            ]);

        $response->assertOk()
            ->assertJson(['status' => 'ok']);

        // Проверяем, что статус команды обновлён
        $command->refresh();
        $this->assertEquals(Command::STATUS_DONE, $command->status);
    }

    public function test_command_ack_endpoint_requires_auth(): void
    {
        // Убеждаемся, что токен не настроен для этого теста
        Config::set('services.python_bridge.ingest_token', null);
        Config::set('services.python_bridge.token', null);
        
        $this->postJson('/api/python/commands/ack', [
            'cmd_id' => 'cmd-test-123',
            'status' => 'completed',
        ])->assertStatus(401);
    }
}
