<?php

declare(strict_types=1);

namespace Tests\Feature\Scheduler;

use App\Models\User;
use App\Models\Zone;
use App\Services\Scheduler\ExecutionChainAssembler;
use Illuminate\Support\Facades\DB;
use Tests\RefreshDatabase;
use Tests\TestCase;

/**
 * Покрывает сервис {@see ExecutionChainAssembler}: успешный, failed, skip,
 * running — 4 сценария из спеки SCHEDULER_COCKPIT_IMPLEMENTATION.md §Ф2.1.
 */
class ExecutionChainTest extends TestCase
{
    use RefreshDatabase;

    private Zone $zone;

    protected function setUp(): void
    {
        parent::setUp();
        $this->zone = Zone::factory()->create();
    }

    public function test_assemble_returns_empty_array_for_unknown_execution(): void
    {
        $assembler = app(ExecutionChainAssembler::class);

        $result = $assembler->assemble($this->zone->id, '999999');

        self::assertSame([], $result);
    }

    public function test_assemble_returns_empty_array_for_invalid_id(): void
    {
        $assembler = app(ExecutionChainAssembler::class);

        self::assertSame([], $assembler->assemble($this->zone->id, ''));
        self::assertSame([], $assembler->assemble($this->zone->id, 'not-a-number'));
    }

    public function test_assemble_builds_full_chain_for_completed_task(): void
    {
        $snapshotId = $this->insertZoneEvent('AE_TASK_SNAPSHOT', [
            'ph' => 6.4,
            'ec' => 1.52,
            'tank_temp_c' => 22.1,
        ]);
        $taskId = $this->insertAeTask([
            'status' => 'completed',
            'current_stage' => 'dosing_acid',
            'corr_snapshot_event_id' => $snapshotId,
            'irrigation_decision_outcome' => 'run',
            'irrigation_decision_strategy' => 'smart_v1',
            'irrigation_bundle_revision' => '3.1.7',
            'completed_at' => now()->toDateTimeString(),
        ]);

        $chain = app(ExecutionChainAssembler::class)->assemble($this->zone->id, (string) $taskId);

        $steps = array_column($chain, 'step');
        self::assertContains('SNAPSHOT', $steps);
        self::assertContains('DECISION', $steps);
        self::assertContains('TASK', $steps);
        self::assertContains('COMPLETE', $steps);

        $snapshot = $this->pickStep($chain, 'SNAPSHOT');
        self::assertSame('ok', $snapshot['status']);
        self::assertStringContainsString('PH=6.4', $snapshot['detail']);
        self::assertStringContainsString('EC=1.52', $snapshot['detail']);

        $decision = $this->pickStep($chain, 'DECISION');
        self::assertSame('ok', $decision['status']);
        self::assertStringContainsString('bundle 3.1.7', $decision['detail']);
        self::assertStringContainsString('strategy=smart_v1', $decision['detail']);
    }

    public function test_assemble_returns_fail_step_for_failed_task(): void
    {
        $taskId = $this->insertAeTask([
            'status' => 'failed',
            'error_code' => 'ACT_TIMEOUT',
            'error_message' => 'pump_acid не ответил 3000ms',
            'completed_at' => now()->toDateTimeString(),
        ]);

        $chain = app(ExecutionChainAssembler::class)->assemble($this->zone->id, (string) $taskId);

        $fail = $this->pickStep($chain, 'FAIL');
        self::assertNotNull($fail);
        self::assertSame('err', $fail['status']);
        self::assertStringContainsString('ACT_TIMEOUT', $fail['detail']);
        self::assertStringContainsString('pump_acid', $fail['detail']);
    }

    public function test_assemble_returns_skip_step_for_completed_skip_decision(): void
    {
        $snapshotId = $this->insertZoneEvent('AE_TASK_SNAPSHOT', ['ec' => 1.52]);
        $taskId = $this->insertAeTask([
            'status' => 'completed',
            'corr_snapshot_event_id' => $snapshotId,
            'irrigation_decision_outcome' => 'skip',
            'irrigation_decision_reason_code' => 'ec_within_band',
            'completed_at' => now()->toDateTimeString(),
        ]);

        $chain = app(ExecutionChainAssembler::class)->assemble($this->zone->id, (string) $taskId);

        $steps = array_column($chain, 'step');
        self::assertSame(['SNAPSHOT', 'DECISION', 'TASK', 'SKIP'], $steps);

        $decision = $this->pickStep($chain, 'DECISION');
        self::assertSame('skip', $decision['status']);

        $skip = $this->pickStep($chain, 'SKIP');
        self::assertSame('skip', $skip['status']);
        self::assertStringContainsString('ec_within_band', $skip['detail']);
    }

    public function test_assemble_marks_running_step_as_live_for_active_task(): void
    {
        $taskId = $this->insertAeTask([
            'status' => 'running',
            'current_stage' => 'dosing_acid',
            'claimed_at' => now()->subSeconds(10)->toDateTimeString(),
        ]);

        $chain = app(ExecutionChainAssembler::class)->assemble($this->zone->id, (string) $taskId);

        $running = $this->pickStep($chain, 'RUNNING');
        self::assertNotNull($running);
        self::assertSame('run', $running['status']);
        self::assertArrayHasKey('live', $running);
        self::assertTrue($running['live']);
    }

    public function test_http_show_includes_chain_field(): void
    {
        $user = User::factory()->create();
        $taskId = $this->insertAeTask([
            'status' => 'completed',
            'completed_at' => now()->toDateTimeString(),
        ]);

        $response = $this->actingAs($user)
            ->getJson("/api/zones/{$this->zone->id}/executions/{$taskId}");

        $response->assertOk();
        $response->assertJsonStructure([
            'status',
            'data' => ['chain'],
        ]);
        $chain = $response->json('data.chain');
        self::assertIsArray($chain);
        self::assertNotEmpty($chain);
    }

    /**
     * @param  array<string, mixed>  $overrides
     */
    private function insertAeTask(array $overrides = []): int
    {
        $now = now();
        $base = [
            'zone_id' => $this->zone->id,
            'task_type' => 'irrigation_start',
            'status' => 'pending',
            'idempotency_key' => 'test-'.uniqid('', true),
            'scheduled_for' => $now->toDateTimeString(),
            'due_at' => $now->copy()->addMinutes(5)->toDateTimeString(),
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
            'created_at' => $now->toDateTimeString(),
            'updated_at' => $now->toDateTimeString(),
        ];

        $id = DB::table('ae_tasks')->insertGetId(array_merge($base, $overrides));

        return (int) $id;
    }

    /**
     * @param  array<string, mixed>  $payload
     */
    private function insertZoneEvent(string $type, array $payload): int
    {
        return (int) DB::table('zone_events')->insertGetId([
            'zone_id' => $this->zone->id,
            'type' => $type,
            'payload_json' => json_encode($payload),
            'created_at' => now()->toDateTimeString(),
        ]);
    }

    /**
     * @param  array<int, array<string, mixed>>  $chain
     * @return array<string, mixed>|null
     */
    private function pickStep(array $chain, string $step): ?array
    {
        foreach ($chain as $entry) {
            if (($entry['step'] ?? null) === $step) {
                return $entry;
            }
        }

        return null;
    }
}
