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

    /**
     * @param  array<string, mixed>  $payload
     */
    private function signedJson(string $uri, array $payload, string $secret, ?int $timestamp = null): \Illuminate\Testing\TestResponse
    {
        $timestamp ??= time();
        $body = json_encode($payload, JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES);
        $signature = hash_hmac('sha256', $timestamp.'.'.$body, $secret);

        return $this->withHeaders([
            'Content-Type' => 'application/json',
            'X-Hydro-Timestamp' => (string) $timestamp,
            'X-Hydro-Signature' => $signature,
            'Accept' => 'application/json',
        ])->call('POST', $uri, [], [], [], [
            'CONTENT_TYPE' => 'application/json',
            'HTTP_ACCEPT' => 'application/json',
        ], $body);
    }

    /**
     * @return array<string, mixed>
     */
    private function aeTaskRow(int $zoneId): array
    {
        return [
            'zone_id' => $zoneId,
            'task_type' => 'irrigation',
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
            'intent_meta' => json_encode(new \stdClass()),
            'created_at' => now()->toDateTimeString(),
            'updated_at' => now()->toDateTimeString(),
        ];
    }
}
