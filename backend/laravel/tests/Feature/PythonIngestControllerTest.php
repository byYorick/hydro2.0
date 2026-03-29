<?php

namespace Tests\Feature;

use App\Jobs\PublishNodeConfigJob;
use App\Models\User;
use App\Models\Zone;
use App\Models\DeviceNode;
use App\Models\Command;
use App\Models\TelemetrySample;
use App\Models\TelemetryLast;
use App\Models\Alert;
use App\Services\AlertPolicyService;
use App\Services\AutomationConfigDocumentService;
use App\Services\AutomationConfigRegistry;
use Tests\RefreshDatabase;
use Illuminate\Support\Facades\Http;
use Illuminate\Support\Facades\Config;
use Illuminate\Support\Facades\Log;
use Illuminate\Support\Facades\Queue;
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
                'status' => 'DONE',
            ]);

        $response->assertOk()
            ->assertJson(['status' => 'ok']);

        // Проверяем, что статус команды обновлён
        $command->refresh();
        $this->assertEquals(Command::STATUS_DONE, $command->status);
    }

    public function test_command_ack_endpoint_returns_404_when_command_not_found(): void
    {
        Config::set('services.python_bridge.ingest_token', 'test-token');

        $this->withHeader('Authorization', 'Bearer test-token')
            ->postJson('/api/python/commands/ack', [
                'cmd_id' => 'cmd-missing-404',
                'status' => 'SENT',
            ])
            ->assertStatus(404)
            ->assertJson([
                'status' => 'error',
                'code' => 'COMMAND_NOT_FOUND',
                'message' => 'Command not found',
            ]);
    }

    public function test_command_ack_endpoint_accepts_timeout_as_terminal_status(): void
    {
        Config::set('services.python_bridge.ingest_token', 'test-token');

        $command = Command::create([
            'cmd_id' => 'cmd-timeout-001',
            'status' => Command::STATUS_ACK,
            'cmd' => 'test_command',
        ]);

        $this->withHeader('Authorization', 'Bearer test-token')
            ->postJson('/api/python/commands/ack', [
                'cmd_id' => 'cmd-timeout-001',
                'status' => 'TIMEOUT',
                'details' => [
                    'error_code' => 'TIMEOUT',
                    'result_code' => 1,
                ],
            ])
            ->assertOk()
            ->assertJson(['status' => 'ok']);

        $command->refresh();
        $this->assertEquals(Command::STATUS_TIMEOUT, $command->status);
        $this->assertNotNull($command->failed_at);
        $this->assertEquals('TIMEOUT', $command->error_code);
        $this->assertEquals(1, $command->result_code);
    }

    public function test_command_ack_endpoint_accepts_send_failed_as_terminal_status(): void
    {
        Config::set('services.python_bridge.ingest_token', 'test-token');

        $command = Command::create([
            'cmd_id' => 'cmd-sendfailed-001',
            'status' => Command::STATUS_QUEUED,
            'cmd' => 'test_command',
        ]);

        $this->withHeader('Authorization', 'Bearer test-token')
            ->postJson('/api/python/commands/ack', [
                'cmd_id' => 'cmd-sendfailed-001',
                'status' => 'SEND_FAILED',
                'details' => [
                    'error_code' => 'SEND_FAILED',
                    'error_message' => 'publish_failed',
                    'result_code' => 1,
                ],
            ])
            ->assertOk()
            ->assertJson(['status' => 'ok']);

        $command->refresh();
        $this->assertEquals(Command::STATUS_SEND_FAILED, $command->status);
        $this->assertNotNull($command->failed_at);
        $this->assertEquals('SEND_FAILED', $command->error_code);
        $this->assertEquals('publish_failed', $command->error_message);
        $this->assertEquals(1, $command->result_code);
    }

    public function test_command_ack_endpoint_prevents_terminal_timeout_to_ack_rollback(): void
    {
        Config::set('services.python_bridge.ingest_token', 'test-token');

        $command = Command::create([
            'cmd_id' => 'cmd-timeout-rollback-001',
            'status' => Command::STATUS_TIMEOUT,
            'cmd' => 'test_command',
        ]);

        $this->withHeader('Authorization', 'Bearer test-token')
            ->postJson('/api/python/commands/ack', [
                'cmd_id' => 'cmd-timeout-rollback-001',
                'status' => 'ACK',
            ])
            ->assertOk()
            ->assertJson([
                'status' => 'ok',
                'message' => 'Command already in final status',
            ]);

        $command->refresh();
        $this->assertEquals(Command::STATUS_TIMEOUT, $command->status);
    }

    public function test_command_ack_endpoint_prevents_done_to_ack_rollback(): void
    {
        Config::set('services.python_bridge.ingest_token', 'test-token');

        $command = Command::create([
            'cmd_id' => 'cmd-done-rollback-001',
            'status' => Command::STATUS_DONE,
            'cmd' => 'test_command',
        ]);

        $this->withHeader('Authorization', 'Bearer test-token')
            ->postJson('/api/python/commands/ack', [
                'cmd_id' => 'cmd-done-rollback-001',
                'status' => 'ACK',
            ])
            ->assertOk()
            ->assertJson([
                'status' => 'ok',
                'message' => 'Command already in final status',
            ]);

        $command->refresh();
        $this->assertEquals(Command::STATUS_DONE, $command->status);
    }

    public function test_command_ack_endpoint_logs_late_sent_after_ack_as_info_not_warning(): void
    {
        Config::set('services.python_bridge.ingest_token', 'test-token');
        Log::spy();

        $command = Command::create([
            'cmd_id' => 'cmd-late-sent-001',
            'status' => Command::STATUS_ACK,
            'cmd' => 'test_command',
        ]);

        $this->withHeader('Authorization', 'Bearer test-token')
            ->postJson('/api/python/commands/ack', [
                'cmd_id' => 'cmd-late-sent-001',
                'status' => 'SENT',
            ])
            ->assertOk()
            ->assertJson([
                'status' => 'ok',
                'message' => 'Status rollback prevented',
            ]);

        $command->refresh();
        $this->assertEquals(Command::STATUS_ACK, $command->status);

        Log::shouldHaveReceived('info')
            ->once()
            ->withArgs(function (string $message, array $context): bool {
                return $message === 'commandAck: Late SENT ignored after ACK'
                    && $context['cmd_id'] === 'cmd-late-sent-001'
                    && $context['current_status'] === Command::STATUS_ACK
                    && $context['attempted_status'] === Command::STATUS_SENT;
            });
        Log::shouldNotHaveReceived('warning', [
            'commandAck: Status rollback prevented by state machine guard',
            \Mockery::any(),
        ]);
    }

    public function test_command_ack_endpoint_requires_auth(): void
    {
        // Убеждаемся, что токен не настроен для этого теста
        Config::set('services.python_bridge.ingest_token', null);
        Config::set('services.python_bridge.token', null);
        
        $this->postJson('/api/python/commands/ack', [
            'cmd_id' => 'cmd-test-123',
            'status' => 'DONE',
        ])->assertStatus(401);
    }

    public function test_config_report_observed_finalizes_pending_bind_in_laravel(): void
    {
        Config::set('services.python_bridge.ingest_token', 'test-token');
        Config::set('services.python_bridge.token', 'test-token');
        Queue::fake([PublishNodeConfigJob::class]);

        $zone = Zone::factory()->create(['uid' => 'zn-target-1']);
        $zone->greenhouse()->update(['uid' => 'gh-target-1']);

        $node = DeviceNode::factory()->create([
            'zone_id' => null,
            'pending_zone_id' => $zone->id,
            'lifecycle_state' => \App\Enums\NodeLifecycleState::REGISTERED_BACKEND,
        ]);

        $response = $this->withHeader('Authorization', 'Bearer test-token')
            ->postJson('/api/python/nodes/config-report-observed', [
                'node_id' => $node->id,
                'node_uid' => $node->uid,
                'gh_uid' => 'gh-target-1',
                'zone_uid' => 'zn-target-1',
                'is_temp_topic' => false,
            ]);

        $response->assertOk()
            ->assertJsonPath('data.finalized', true)
            ->assertJsonPath('data.zone_id', $zone->id);

        $node->refresh();
        $this->assertSame($zone->id, $node->zone_id);
        $this->assertNull($node->pending_zone_id);
        $this->assertSame('ASSIGNED_TO_ZONE', $node->lifecycle_state->value);
    }

    public function test_config_report_observed_defers_on_namespace_mismatch(): void
    {
        Config::set('services.python_bridge.ingest_token', 'test-token');
        Config::set('services.python_bridge.token', 'test-token');
        Queue::fake([PublishNodeConfigJob::class]);

        $zone = Zone::factory()->create(['uid' => 'zn-target-2']);
        $zone->greenhouse()->update(['uid' => 'gh-target-2']);

        $node = DeviceNode::factory()->create([
            'zone_id' => null,
            'pending_zone_id' => $zone->id,
            'lifecycle_state' => \App\Enums\NodeLifecycleState::REGISTERED_BACKEND,
        ]);

        $response = $this->withHeader('Authorization', 'Bearer test-token')
            ->postJson('/api/python/nodes/config-report-observed', [
                'node_id' => $node->id,
                'node_uid' => $node->uid,
                'gh_uid' => 'gh-old',
                'zone_uid' => 'zn-old',
                'is_temp_topic' => false,
            ]);

        $response->assertOk()
            ->assertJsonPath('data.finalized', false)
            ->assertJsonPath('data.reason', 'namespace_mismatch');

        $node->refresh();
        $this->assertNull($node->zone_id);
        $this->assertSame($zone->id, $node->pending_zone_id);
        $this->assertSame('REGISTERED_BACKEND', $node->lifecycle_state->value);
    }

    public function test_config_report_observed_recovers_inconsistent_pending_bind(): void
    {
        Config::set('services.python_bridge.ingest_token', 'test-token');
        Config::set('services.python_bridge.token', 'test-token');
        Queue::fake([PublishNodeConfigJob::class]);

        $zone = Zone::factory()->create(['uid' => 'zn-target-3']);
        $zone->greenhouse()->update(['uid' => 'gh-target-3']);

        $node = DeviceNode::factory()->create([
            'zone_id' => null,
            'pending_zone_id' => $zone->id,
            'lifecycle_state' => \App\Enums\NodeLifecycleState::ASSIGNED_TO_ZONE,
        ]);

        $response = $this->withHeader('Authorization', 'Bearer test-token')
            ->postJson('/api/python/nodes/config-report-observed', [
                'node_id' => $node->id,
                'node_uid' => $node->uid,
                'gh_uid' => 'gh-target-3',
                'zone_uid' => 'zn-target-3',
                'is_temp_topic' => false,
            ]);

        $response->assertOk()
            ->assertJsonPath('data.finalized', true);

        $node->refresh();
        $this->assertSame($zone->id, $node->zone_id);
        $this->assertNull($node->pending_zone_id);
        $this->assertSame('ASSIGNED_TO_ZONE', $node->lifecycle_state->value);
    }

    public function test_config_report_observed_rejects_node_uid_mismatch(): void
    {
        Config::set('services.python_bridge.ingest_token', 'test-token');
        Config::set('services.python_bridge.token', 'test-token');
        Queue::fake([PublishNodeConfigJob::class]);

        $zone = Zone::factory()->create(['uid' => 'zn-target-4']);
        $zone->greenhouse()->update(['uid' => 'gh-target-4']);

        $node = DeviceNode::factory()->create([
            'zone_id' => null,
            'pending_zone_id' => $zone->id,
            'lifecycle_state' => \App\Enums\NodeLifecycleState::REGISTERED_BACKEND,
        ]);

        $response = $this->withHeader('Authorization', 'Bearer test-token')
            ->postJson('/api/python/nodes/config-report-observed', [
                'node_id' => $node->id,
                'node_uid' => 'nd-other-node',
                'gh_uid' => 'gh-target-4',
                'zone_uid' => 'zn-target-4',
                'is_temp_topic' => false,
            ]);

        $response->assertStatus(422)
            ->assertJsonPath('status', 'error')
            ->assertJsonPath('message', 'node_uid does not match node_id');

        $node->refresh();
        $this->assertNull($node->zone_id);
        $this->assertSame($zone->id, $node->pending_zone_id);
        $this->assertSame('REGISTERED_BACKEND', $node->lifecycle_state->value);
    }

    public function test_alerts_endpoint_returns_202_when_rate_limited(): void
    {
        Config::set('services.python_bridge.ingest_token', 'test-token');
        Config::set('services.python_bridge.token', 'test-token');
        Config::set('alerts.rate_limiting.enabled', true);
        Config::set('alerts.rate_limiting.max_per_minute', 0);
        Config::set('alerts.rate_limiting.critical_codes', []);

        $zone = Zone::factory()->create();

        $response = $this->withHeader('Authorization', 'Bearer test-token')
            ->postJson('/api/python/alerts', [
                'zone_id' => $zone->id,
                'source' => 'infra',
                'code' => 'infra_rate_limited_test',
                'type' => 'Infrastructure Error',
                'status' => 'ACTIVE',
                'details' => ['message' => 'test'],
            ]);

        $response->assertStatus(202)
            ->assertJsonPath('data.rate_limited', true);

        $this->assertDatabaseMissing('alerts', [
            'zone_id' => $zone->id,
            'code' => 'infra_rate_limited_test',
            'status' => 'ACTIVE',
        ]);
    }

    public function test_alerts_endpoint_resolves_active_alert_with_status_resolved(): void
    {
        Config::set('services.python_bridge.ingest_token', 'test-token');
        Config::set('services.python_bridge.token', 'test-token');

        $zone = Zone::factory()->create();
        $alert = Alert::factory()->create([
            'zone_id' => $zone->id,
            'source' => 'infra',
            'code' => 'infra_resolve_test',
            'type' => 'Infrastructure Error',
            'status' => 'ACTIVE',
        ]);

        $response = $this->withHeader('Authorization', 'Bearer test-token')
            ->postJson('/api/python/alerts', [
                'zone_id' => $zone->id,
                'source' => 'infra',
                'code' => 'infra_resolve_test',
                'type' => 'Infrastructure Error',
                'status' => 'RESOLVED',
                'details' => ['reason' => 'recovered'],
            ]);

        $response->assertOk()
            ->assertJsonPath('data.resolved', true)
            ->assertJsonPath('data.alert_id', $alert->id);

        $this->assertDatabaseHas('alerts', [
            'id' => $alert->id,
            'status' => 'RESOLVED',
        ]);

        $alert->refresh();
        $this->assertSame('python_ingest', $alert->details['resolved_by'] ?? null);
        $this->assertSame('auto', $alert->details['resolved_via'] ?? null);
        $this->assertSame('infra', $alert->details['resolved_source'] ?? null);
    }

    public function test_alerts_endpoint_accepts_node_source_and_normalizes_severity(): void
    {
        Config::set('services.python_bridge.ingest_token', 'test-token');
        Config::set('services.python_bridge.token', 'test-token');

        $zone = Zone::factory()->create();

        $response = $this->withHeader('Authorization', 'Bearer test-token')
            ->postJson('/api/python/alerts', [
                'zone_id' => $zone->id,
                'source' => 'node',
                'code' => 'node_error_sensor_timeout',
                'type' => 'node_error',
                'severity' => 'CRITICAL',
                'node_uid' => 'nd-node-1',
                'hardware_id' => 'esp32-node-1',
                'status' => 'active',
                'details' => ['message' => 'Node timeout'],
            ]);

        $response->assertOk()
            ->assertJsonPath('status', 'ok');

        $this->assertDatabaseHas('alerts', [
            'zone_id' => $zone->id,
            'source' => 'node',
            'code' => 'node_error_sensor_timeout',
            'status' => 'ACTIVE',
            'severity' => 'critical',
            'category' => 'node',
            'node_uid' => 'nd-node-1',
            'hardware_id' => 'esp32-node-1',
        ]);
    }

    public function test_alerts_endpoint_blocks_policy_managed_biz_auto_resolution_in_manual_mode(): void
    {
        Config::set('services.python_bridge.ingest_token', 'test-token');
        Config::set('services.python_bridge.token', 'test-token');

        $zone = Zone::factory()->create();
        $alert = Alert::factory()->create([
            'zone_id' => $zone->id,
            'source' => 'biz',
            'code' => 'biz_zone_correction_config_missing',
            'type' => 'automation_engine',
            'status' => 'ACTIVE',
        ]);

        $response = $this->withHeader('Authorization', 'Bearer test-token')
            ->postJson('/api/python/alerts', [
                'zone_id' => $zone->id,
                'source' => 'biz',
                'code' => 'biz_zone_correction_config_missing',
                'type' => 'automation_engine',
                'status' => 'RESOLVED',
                'details' => ['reason' => 'recovered'],
            ]);

        $response->assertOk()
            ->assertJsonPath('data.resolved', false)
            ->assertJsonPath('data.blocked_by_policy', true)
            ->assertJsonPath('data.policy_mode', AlertPolicyService::MODE_MANUAL_ACK);

        $alert->refresh();
        $this->assertSame('ACTIVE', $alert->status);
    }

    public function test_alerts_endpoint_allows_eligible_biz_auto_resolution_when_policy_enabled(): void
    {
        Config::set('services.python_bridge.ingest_token', 'test-token');
        Config::set('services.python_bridge.token', 'test-token');
        app(AutomationConfigDocumentService::class)->upsertDocument(
            AutomationConfigRegistry::NAMESPACE_SYSTEM_ALERT_POLICIES,
            AutomationConfigRegistry::SCOPE_SYSTEM,
            0,
            [
                'ae3_operational_resolution_mode' => AlertPolicyService::MODE_AUTO_RESOLVE_ON_RECOVERY,
            ]
        );

        $zone = Zone::factory()->create();
        $alert = Alert::factory()->create([
            'zone_id' => $zone->id,
            'source' => 'biz',
            'code' => 'biz_zone_correction_config_missing',
            'type' => 'automation_engine',
            'status' => 'ACTIVE',
        ]);

        $response = $this->withHeader('Authorization', 'Bearer test-token')
            ->postJson('/api/python/alerts', [
                'zone_id' => $zone->id,
                'source' => 'biz',
                'code' => 'biz_zone_correction_config_missing',
                'type' => 'automation_engine',
                'status' => 'RESOLVED',
                'details' => ['reason' => 'recovered'],
            ]);

        $response->assertOk()
            ->assertJsonPath('data.resolved', true)
            ->assertJsonPath('data.blocked_by_policy', false);

        $alert->refresh();
        $this->assertSame('RESOLVED', $alert->status);
    }
}
