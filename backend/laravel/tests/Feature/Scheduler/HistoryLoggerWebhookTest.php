<?php

declare(strict_types=1);

namespace Tests\Feature\Scheduler;

use App\Events\ExecutionChainUpdated;
use App\Models\Zone;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Event;
use Tests\RefreshDatabase;
use Tests\TestCase;

/**
 * Покрывает webhook от history-logger-а для live-обновлений causal chain.
 */
class HistoryLoggerWebhookTest extends TestCase
{
    use RefreshDatabase;

    private const SECRET = 'test-webhook-secret';

    protected function setUp(): void
    {
        parent::setUp();
        config(['services.history_logger.webhook_secret' => self::SECRET]);
    }

    public function test_missing_signature_headers_returns_401(): void
    {
        $response = $this->postJson('/api/internal/webhooks/history-logger/execution-event', [
            'zone_id' => 1,
            'execution_id' => '1',
            'step' => 'DISPATCH',
            'ref' => 'cmd-1',
            'status' => 'ok',
        ]);

        $response->assertStatus(401);
    }

    public function test_invalid_signature_returns_401(): void
    {
        $response = $this->signedJson('/api/internal/webhooks/history-logger/execution-event', [
            'zone_id' => 1,
            'execution_id' => '1',
            'step' => 'DISPATCH',
            'ref' => 'cmd-1',
            'status' => 'ok',
        ], secret: 'wrong-secret');

        $response->assertStatus(401);
    }

    public function test_stale_timestamp_rejected(): void
    {
        $response = $this->signedJson(
            '/api/internal/webhooks/history-logger/execution-event',
            [
                'zone_id' => 1,
                'execution_id' => '1',
                'step' => 'DISPATCH',
                'ref' => 'cmd-1',
                'status' => 'ok',
            ],
            secret: self::SECRET,
            timestamp: time() - 3600,
        );

        $response->assertStatus(401);
    }

    public function test_valid_webhook_broadcasts_event(): void
    {
        Event::fake([ExecutionChainUpdated::class]);
        $zone = Zone::factory()->create();
        $taskId = DB::table('ae_tasks')->insertGetId($this->aeTaskRow($zone->id));

        $response = $this->signedJson(
            '/api/internal/webhooks/history-logger/execution-event',
            [
                'zone_id' => $zone->id,
                'execution_id' => (string) $taskId,
                'step' => 'DISPATCH',
                'ref' => 'cmd-9931',
                'status' => 'ok',
                'detail' => 'history-logger → mqtt',
                'live' => false,
            ],
            secret: self::SECRET,
        );

        $response->assertOk();
        $response->assertJson(['status' => 'ok']);
        Event::assertDispatched(ExecutionChainUpdated::class, function (ExecutionChainUpdated $event) use ($zone, $taskId): bool {
            return $event->zoneId === $zone->id
                && $event->executionId === (string) $taskId
                && ($event->step['step'] ?? null) === 'DISPATCH'
                && ($event->step['ref'] ?? null) === 'cmd-9931';
        });
    }

    public function test_validation_rejects_unknown_step_type(): void
    {
        $response = $this->signedJson(
            '/api/internal/webhooks/history-logger/execution-event',
            [
                'zone_id' => 1,
                'execution_id' => '1',
                'step' => 'NOT_A_STEP',
                'ref' => 'cmd-1',
                'status' => 'ok',
            ],
            secret: self::SECRET,
        );

        $response->assertStatus(422);
    }

    public function test_validation_rejects_payload_without_execution_id_or_cmd_id(): void
    {
        $response = $this->signedJson(
            '/api/internal/webhooks/history-logger/execution-event',
            [
                'zone_id' => 1,
                'step' => 'DISPATCH',
                'ref' => 'cmd-1',
                'status' => 'ok',
            ],
            secret: self::SECRET,
        );

        $response->assertStatus(422);
    }

    public function test_resolves_execution_id_from_cmd_id_via_corr_snapshot(): void
    {
        Event::fake([ExecutionChainUpdated::class]);
        $zone = Zone::factory()->create();
        $cmdId = 'cmd-corr-'.uniqid('', true);

        $taskId = DB::table('ae_tasks')->insertGetId(array_merge(
            $this->aeTaskRow($zone->id),
            ['corr_snapshot_cmd_id' => $cmdId],
        ));

        $response = $this->signedJson(
            '/api/internal/webhooks/history-logger/execution-event',
            [
                'zone_id' => $zone->id,
                'cmd_id' => $cmdId,
                'step' => 'DISPATCH',
                'ref' => 'cmd-'.$cmdId,
                'status' => 'ok',
            ],
            secret: self::SECRET,
        );

        $response->assertOk();
        $response->assertJson(['status' => 'ok', 'execution_id' => (string) $taskId]);
        Event::assertDispatched(ExecutionChainUpdated::class, fn (ExecutionChainUpdated $event): bool => $event->executionId === (string) $taskId);
    }

    public function test_unresolvable_cmd_id_returns_ok_with_unresolved_flag(): void
    {
        Event::fake([ExecutionChainUpdated::class]);
        $zone = Zone::factory()->create();

        $response = $this->signedJson(
            '/api/internal/webhooks/history-logger/execution-event',
            [
                'zone_id' => $zone->id,
                'cmd_id' => 'cmd-orphan-'.uniqid('', true),
                'step' => 'DISPATCH',
                'ref' => 'cmd-orphan',
                'status' => 'ok',
            ],
            secret: self::SECRET,
        );

        $response->assertOk();
        $response->assertJson(['status' => 'ok', 'unresolved' => true]);
        Event::assertNotDispatched(ExecutionChainUpdated::class);
    }

    /**
     * @param  array<string, mixed>  $payload
     */
    private function signedJson(string $uri, array $payload, string $secret, ?int $timestamp = null): \Illuminate\Testing\TestResponse
    {
        $timestamp ??= time();
        // Laravel postJson сам сформирует тело через json_encode($payload) без
        // спец-флагов. Используем точно такую же кодировку для HMAC.
        $body = json_encode($payload);
        $signature = hash_hmac('sha256', $timestamp.'.'.$body, $secret);

        return $this->withHeaders([
            'X-Hydro-Timestamp' => (string) $timestamp,
            'X-Hydro-Signature' => $signature,
        ])->postJson($uri, $payload);
    }

    /**
     * @return array<string, mixed>
     */
    private function aeTaskRow(int $zoneId): array
    {
        return [
            'zone_id' => $zoneId,
            'task_type' => 'irrigation_start',
            'status' => 'running',
            'idempotency_key' => 'wh-'.uniqid('', true),
            'scheduled_for' => now()->toDateTimeString(),
            'due_at' => now()->addMinutes(5)->toDateTimeString(),
            'topology' => 'two_tank',
            'current_stage' => 'startup',
            'workflow_phase' => 'idle',
            'stage_retry_count' => 0,
            'clean_fill_cycle' => 0,
            'corr_limit_policy_logged' => false,
            'irrigation_replay_count' => 0,
            'corr_ec_current_seq_index' => 0,
            'start_event_emitted' => false,
            'irr_probe_failure_streak' => 0,
            'intent_meta' => json_encode(new \stdClass),
            'created_at' => now()->toDateTimeString(),
            'updated_at' => now()->toDateTimeString(),
        ];
    }
}
