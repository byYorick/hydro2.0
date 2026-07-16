<?php

namespace Tests\Unit\Services;

use App\Models\Zone;
use App\Services\ZoneAutomationObservabilityService;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Illuminate\Support\Carbon;
use Illuminate\Support\Facades\DB;
use Tests\TestCase;

class ZoneAutomationObservabilityServiceTest extends TestCase
{
    use RefreshDatabase;

    public function test_enrich_payload_adds_scheduler_pending_hint(): void
    {
        Carbon::setTestNow(Carbon::parse('2026-06-23 12:00:00'));

        $zone = Zone::factory()->create();

        DB::table('zone_automation_intents')->insert([
            'zone_id' => $zone->id,
            'intent_type' => 'cycle_start',
            'status' => 'pending',
            'idempotency_key' => 'obs-intent-1',
            'not_before' => now()->subMinutes(10),
            'created_at' => now()->subMinutes(10),
            'updated_at' => now()->subMinutes(10),
        ]);

        $service = app(ZoneAutomationObservabilityService::class);
        $payload = $service->enrichPayload($zone->id, [
            'observability' => [
                'runtime' => ['task_is_active' => false],
                'hang_hints' => [],
                'overall_health' => 'idle',
            ],
        ]);

        $this->assertSame(1, $payload['observability']['scheduler']['pending_count']);
        $this->assertTrue(
            collect($payload['observability']['hang_hints'])
                ->contains(fn (array $hint): bool => ($hint['code'] ?? '') === 'scheduler_intent_pending')
        );
        $this->assertSame('warning', $payload['observability']['overall_health']);
    }

    public function test_enrich_payload_builds_fallback_when_observability_missing(): void
    {
        $zone = Zone::factory()->create();

        $service = app(ZoneAutomationObservabilityService::class);
        $payload = $service->enrichPayload($zone->id, [
            'zone_id' => $zone->id,
            'workflow_phase' => 'idle',
            'state_details' => ['elapsed_sec' => 0],
        ]);

        $this->assertIsArray($payload['observability']['runtime'] ?? null);
        $this->assertIsArray($payload['observability']['scheduler'] ?? null);
        $this->assertSame('idle', $payload['observability']['overall_health']);
    }

    public function test_runtime_hang_hints_detect_waiting_command_stuck(): void
    {
        $service = app(ZoneAutomationObservabilityService::class);
        $method = new \ReflectionMethod($service, 'runtimeHangHints');
        $method->setAccessible(true);

        /** @var list<array<string,mixed>> $hints */
        $hints = $method->invoke($service, [
            'task_is_active' => true,
            'task_status' => 'waiting_command',
            'waiting_command' => true,
            'waiting_elapsed_sec' => 240,
            'current_stage' => 'clean_fill_check',
            'stage_elapsed_sec' => 480,
        ]);

        $codes = array_column($hints, 'code');
        $this->assertContains('waiting_command_stuck', $codes);
        $this->assertContains('stage_elapsed_long', $codes);
    }

    public function test_runtime_hang_hints_skip_stage_elapsed_long_for_irrigation_within_deadline(): void
    {
        $service = app(ZoneAutomationObservabilityService::class);
        $method = new \ReflectionMethod($service, 'runtimeHangHints');
        $method->setAccessible(true);

        /** @var list<array<string,mixed>> $hints */
        $hints = $method->invoke($service, [
            'task_is_active' => true,
            'task_status' => 'running',
            'waiting_command' => false,
            'current_stage' => 'irrigation_check',
            'stage_elapsed_sec' => 362,
            'stage_deadline_remaining_sec' => 628,
        ]);

        $codes = array_column($hints, 'code');
        $this->assertNotContains('stage_elapsed_long', $codes);
    }

    public function test_build_runtime_from_database_deadline_remaining_sign_matches_ae3(): void
    {
        Carbon::setTestNow(Carbon::parse('2026-06-23 12:00:00'));

        $zone = Zone::factory()->create();
        $now = now();

        $taskId = DB::table('ae_tasks')->insertGetId([
            'zone_id' => $zone->id,
            'task_type' => 'cycle_start',
            'status' => 'running',
            'idempotency_key' => 'obs-deadline-sign',
            'topology' => 'two_tank_drip_substrate_trays',
            'current_stage' => 'irrigation_check',
            'workflow_phase' => 'irrigating',
            'control_mode_snapshot' => 'auto',
            'scheduled_for' => $now,
            'due_at' => $now,
            'stage_entered_at' => $now->copy()->subMinutes(2),
            'stage_deadline_at' => $now->copy()->addMinutes(10),
            'created_at' => $now->copy()->subMinutes(5),
            'updated_at' => $now->copy()->subMinute(),
        ]);

        $service = app(ZoneAutomationObservabilityService::class);
        $method = new \ReflectionMethod($service, 'buildRuntimeFromDatabase');
        $method->setAccessible(true);

        /** @var array<string,mixed> $runtime */
        $runtime = $method->invoke($service, $zone->id, [], true);

        $this->assertSame($taskId, $runtime['task_id']);
        // AE3 contract: remaining = deadline - now (positive while deadline is ahead).
        $this->assertGreaterThan(0, (int) $runtime['stage_deadline_remaining_sec']);
        $this->assertEqualsWithDelta(600, (int) $runtime['stage_deadline_remaining_sec'], 2);

        Carbon::setTestNow();
    }

    public function test_enrich_payload_adds_scheduler_claimed_stuck_hint(): void
    {
        Carbon::setTestNow(Carbon::parse('2026-06-23 12:00:00'));

        $zone = Zone::factory()->create();

        DB::table('zone_automation_intents')->insert([
            'zone_id' => $zone->id,
            'intent_type' => 'cycle_start',
            'status' => 'claimed',
            'idempotency_key' => 'obs-intent-claimed',
            'not_before' => now()->subMinutes(10),
            'claimed_at' => now()->subMinutes(5),
            'created_at' => now()->subMinutes(10),
            'updated_at' => now()->subMinutes(5),
        ]);

        $service = app(ZoneAutomationObservabilityService::class);
        $payload = $service->enrichPayload($zone->id, [
            'observability' => [
                'runtime' => ['task_is_active' => false],
                'hang_hints' => [],
                'overall_health' => 'idle',
            ],
        ]);

        $this->assertTrue(
            collect($payload['observability']['hang_hints'])
                ->contains(fn (array $hint): bool => ($hint['code'] ?? '') === 'scheduler_intent_claimed_stuck')
        );

        Carbon::setTestNow();
    }

    public function test_enrich_payload_adds_scheduler_running_stuck_hint(): void
    {
        Carbon::setTestNow(Carbon::parse('2026-06-23 12:00:00'));

        $zone = Zone::factory()->create();

        DB::table('zone_automation_intents')->insert([
            'zone_id' => $zone->id,
            'intent_type' => 'cycle_start',
            'status' => 'running',
            'idempotency_key' => 'obs-intent-running',
            'not_before' => now()->subMinutes(20),
            'claimed_at' => now()->subMinutes(20),
            'created_at' => now()->subMinutes(20),
            'updated_at' => now()->subMinutes(12),
        ]);

        $service = app(ZoneAutomationObservabilityService::class);
        $payload = $service->enrichPayload($zone->id, [
            'observability' => [
                'runtime' => ['task_is_active' => true, 'task_status' => 'running'],
                'hang_hints' => [],
                'overall_health' => 'active',
            ],
        ]);

        $this->assertTrue(
            collect($payload['observability']['hang_hints'])
                ->contains(fn (array $hint): bool => ($hint['code'] ?? '') === 'scheduler_intent_running_stuck')
        );

        Carbon::setTestNow();
    }

    public function test_enrich_payload_on_stale_replaces_ae_runtime_from_database(): void
    {
        Carbon::setTestNow(Carbon::parse('2026-06-23 12:00:00'));

        $zone = Zone::factory()->create();
        $now = now();

        DB::table('ae_tasks')->insert([
            'zone_id' => $zone->id,
            'task_type' => 'cycle_start',
            'status' => 'waiting_command',
            'idempotency_key' => 'obs-stale-merge',
            'topology' => 'two_tank_drip_substrate_trays',
            'current_stage' => 'clean_fill_check',
            'workflow_phase' => 'tank_filling',
            'control_mode_snapshot' => 'auto',
            'scheduled_for' => $now,
            'due_at' => $now,
            'stage_entered_at' => $now->copy()->subMinutes(2),
            'created_at' => $now->copy()->subMinutes(2),
            'updated_at' => $now->copy()->subMinutes(3),
        ]);

        $service = app(ZoneAutomationObservabilityService::class);
        $payload = $service->enrichPayload($zone->id, [
            'workflow_phase' => 'tank_filling',
            'current_stage' => 'clean_fill_check',
            'state_details' => ['elapsed_sec' => 120],
            'observability' => [
                'runtime' => [
                    'task_is_active' => true,
                    'task_status' => 'running',
                    'waiting_command' => false,
                    'current_stage' => 'clean_fill_check',
                    'stage_elapsed_sec' => 120,
                ],
                'hang_hints' => [
                    [
                        'code' => 'stage_elapsed_long',
                        'severity' => 'warning',
                        'message' => 'Устаревший hint из AE-кэша',
                    ],
                ],
                'overall_health' => 'warning',
            ],
        ], isStale: true);

        $this->assertSame('waiting_command', $payload['observability']['runtime']['task_status']);
        $this->assertTrue($payload['observability']['runtime']['waiting_command']);
        $this->assertSame('laravel_db_fallback', $payload['observability']['runtime']['source']);

        $codes = collect($payload['observability']['hang_hints'])->pluck('code')->all();
        $this->assertContains('waiting_command_stuck', $codes);
        $this->assertNotContains('stage_elapsed_long', $codes);

        Carbon::setTestNow();
    }

    public function test_enrich_payload_skips_laravel_runtime_hints_for_live_ae_observability(): void
    {
        $service = app(ZoneAutomationObservabilityService::class);
        $payload = $service->enrichPayload(1, [
            'observability' => [
                'runtime' => [
                    'task_is_active' => true,
                    'task_status' => 'running',
                    'current_stage' => 'solution_fill_check',
                    'stage_elapsed_sec' => 400,
                    'waiting_command' => false,
                ],
                'hang_hints' => [],
                'overall_health' => 'active',
            ],
        ], isStale: false);

        $codes = collect($payload['observability']['hang_hints'])->pluck('code')->all();
        $this->assertNotContains('stage_elapsed_long', $codes);
        $this->assertSame('active', $payload['observability']['overall_health']);
    }

    public function test_enrich_payload_adds_scheduler_intent_task_drift_hint(): void
    {
        $zone = Zone::factory()->create();
        $key = 'drift-hint-test';
        $dueAt = now()->subMinutes(3);

        DB::table('zone_automation_intents')->insert([
            'zone_id' => $zone->id,
            'intent_type' => 'DIAGNOSTICS_TICK',
            'task_type' => 'cycle_start',
            'intent_source' => 'laravel_scheduler',
            'idempotency_key' => $key,
            'status' => 'running',
            'not_before' => now(),
            'retry_count' => 0,
            'max_retries' => 3,
            'created_at' => now()->subMinutes(5),
            'updated_at' => now()->subMinutes(2),
        ]);

        $intentId = (int) DB::table('zone_automation_intents')->where('zone_id', $zone->id)->value('id');

        DB::table('ae_tasks')->insert([
            'zone_id' => $zone->id,
            'task_type' => 'cycle_start',
            'status' => 'pending',
            'idempotency_key' => $key,
            'intent_id' => $intentId,
            'scheduled_for' => $dueAt,
            'due_at' => $dueAt,
            'created_at' => now()->subMinutes(5),
            'updated_at' => $dueAt,
        ]);

        $service = app(ZoneAutomationObservabilityService::class);
        $payload = $service->enrichPayload($zone->id, [
            'zone_id' => $zone->id,
            'state' => 'TANK_FILLING',
            'state_details' => ['failed' => false],
        ], isStale: false);

        $codes = collect($payload['observability']['hang_hints'])->pluck('code')->all();
        $this->assertContains('scheduler_intent_task_drift', $codes);
    }

    public function test_enrich_payload_skips_scheduler_intent_task_drift_during_two_tank_requeue_window(): void
    {
        $zone = Zone::factory()->create();
        $key = 'drift-hint-requeue-window';

        DB::table('zone_automation_intents')->insert([
            'zone_id' => $zone->id,
            'intent_type' => 'DIAGNOSTICS_TICK',
            'task_type' => 'cycle_start',
            'intent_source' => 'laravel_scheduler',
            'idempotency_key' => $key,
            'status' => 'running',
            'not_before' => now(),
            'retry_count' => 0,
            'max_retries' => 3,
            'created_at' => now()->subMinute(),
            'updated_at' => now(),
        ]);

        $intentId = (int) DB::table('zone_automation_intents')->where('zone_id', $zone->id)->value('id');
        $dueAt = now()->addSeconds(30);

        DB::table('ae_tasks')->insert([
            'zone_id' => $zone->id,
            'task_type' => 'cycle_start',
            'status' => 'pending',
            'idempotency_key' => $key,
            'intent_id' => $intentId,
            'scheduled_for' => $dueAt,
            'due_at' => $dueAt,
            'created_at' => now()->subMinute(),
            'updated_at' => now(),
        ]);

        $service = app(ZoneAutomationObservabilityService::class);
        $payload = $service->enrichPayload($zone->id, [
            'zone_id' => $zone->id,
            'state' => 'TANK_FILLING',
            'state_details' => ['failed' => false],
        ], isStale: false);

        $codes = collect($payload['observability']['hang_hints'])->pluck('code')->all();
        $this->assertNotContains('scheduler_intent_task_drift', $codes);
    }

    public function test_enrich_payload_adds_correction_context_from_zone_events_and_pid_state(): void
    {
        Carbon::setTestNow(Carbon::parse('2026-07-09 12:00:00'));

        $zone = Zone::factory()->create();

        DB::table('pid_state')->insert([
            'zone_id' => $zone->id,
            'pid_type' => 'ec',
            'last_dose_at' => now()->subMinutes(2),
            'no_effect_count' => 1,
            'created_at' => now(),
            'updated_at' => now(),
        ]);

        DB::table('zone_events')->insert([
            'zone_id' => $zone->id,
            'type' => 'CORRECTION_SKIPPED_COOLDOWN',
            'payload_json' => json_encode([
                'retry_after_sec' => 60,
                'reason' => 'min_interval',
                'task_id' => 42,
            ]),
            'created_at' => now()->subSeconds(15),
        ]);

        DB::table('zone_events')->insert([
            'zone_id' => $zone->id,
            'type' => 'CORRECTION_COMPLETE',
            'payload_json' => json_encode([
                'targets_in_tolerance' => true,
                'workflow_ready' => false,
                'task_id' => 42,
            ]),
            'created_at' => now()->subSeconds(5),
        ]);

        $service = app(ZoneAutomationObservabilityService::class);
        $payload = $service->enrichPayload($zone->id, [
            'observability' => [
                'runtime' => [
                    'task_is_active' => true,
                    'task_id' => 42,
                    'correction_step' => 'corr_check',
                ],
                'hang_hints' => [],
                'overall_health' => 'active',
            ],
        ]);

        $correction = $payload['observability']['correction'] ?? null;
        $this->assertIsArray($correction);
        $this->assertSame('CORRECTION_SKIPPED_COOLDOWN', $correction['latest_skip']['event_type'] ?? null);
        $this->assertSame(60, $correction['latest_skip']['payload']['retry_after_sec'] ?? null);
        $this->assertSame(42, $correction['latest_skip']['payload']['task_id'] ?? null);
        $this->assertTrue($correction['readiness']['targets_in_tolerance'] ?? false);
        $this->assertFalse($correction['readiness']['workflow_ready'] ?? true);
        $this->assertArrayHasKey('ec', $correction['last_dose'] ?? []);
    }

    public function test_correction_skip_prefers_active_task_and_ignores_stale(): void
    {
        Carbon::setTestNow(Carbon::parse('2026-07-09 12:00:00'));

        $zone = Zone::factory()->create();

        // Stale event from another task (older than max age window would be filtered;
        // here: different task_id should lose to active task).
        DB::table('zone_events')->insert([
            'zone_id' => $zone->id,
            'type' => 'CORRECTION_SKIPPED_COOLDOWN',
            'payload_json' => json_encode(['retry_after_sec' => 30, 'task_id' => 7]),
            'created_at' => now()->subSeconds(20),
        ]);

        DB::table('zone_events')->insert([
            'zone_id' => $zone->id,
            'type' => 'EC_BATCH_PARTIAL_FAILURE',
            'payload_json' => json_encode([
                'status' => 'degraded',
                'failed_component' => 'magnesium',
                'task_id' => 99,
            ]),
            'created_at' => now()->subSeconds(10),
        ]);

        $service = app(ZoneAutomationObservabilityService::class);
        $payload = $service->enrichPayload($zone->id, [
            'observability' => [
                'runtime' => ['task_is_active' => true, 'task_id' => 99],
                'hang_hints' => [],
                'overall_health' => 'active',
            ],
        ]);

        $skip = $payload['observability']['correction']['latest_skip'] ?? null;
        $this->assertIsArray($skip);
        $this->assertSame('EC_BATCH_PARTIAL_FAILURE', $skip['event_type'] ?? null);
        $this->assertSame('magnesium', $skip['payload']['failed_component'] ?? null);
    }

    public function test_enrich_payload_backfills_empty_timeline_from_zone_events(): void
    {
        Carbon::setTestNow(Carbon::parse('2026-07-16 12:00:00'));

        $zone = Zone::factory()->create();

        DB::table('zone_events')->insert([
            'zone_id' => $zone->id,
            'type' => 'TWO_TANK_STARTUP_INITIATED',
            'payload_json' => json_encode(['task_id' => 11]),
            'created_at' => now()->subMinutes(30),
        ]);
        DB::table('zone_events')->insert([
            'zone_id' => $zone->id,
            'type' => 'CLEAN_FILL_COMPLETED',
            'payload_json' => json_encode(['task_id' => 11]),
            'created_at' => now()->subMinutes(10),
        ]);
        DB::table('zone_events')->insert([
            'zone_id' => $zone->id,
            'type' => 'SOME_NOISE_EVENT',
            'payload_json' => json_encode([]),
            'created_at' => now()->subMinutes(5),
        ]);

        $service = app(ZoneAutomationObservabilityService::class);
        $payload = $service->enrichPayload($zone->id, [
            'timeline' => [],
            'observability' => [
                'runtime' => ['task_is_active' => false],
                'hang_hints' => [],
                'overall_health' => 'idle',
            ],
        ]);

        $timeline = $payload['timeline'] ?? null;
        $this->assertIsArray($timeline);
        $this->assertCount(2, $timeline);
        $this->assertSame('TWO_TANK_STARTUP_INITIATED', $timeline[0]['event'] ?? null);
        $this->assertSame('CLEAN_FILL_COMPLETED', $timeline[1]['event'] ?? null);
        $this->assertFalse($timeline[0]['active'] ?? true);
        $this->assertTrue($timeline[1]['active'] ?? false);
        $this->assertSame('Бак чистой воды заполнен', $timeline[1]['label'] ?? null);
    }

    public function test_enrich_payload_does_not_overwrite_non_empty_timeline(): void
    {
        Carbon::setTestNow(Carbon::parse('2026-07-16 12:00:00'));

        $zone = Zone::factory()->create();

        DB::table('zone_events')->insert([
            'zone_id' => $zone->id,
            'type' => 'CLEAN_FILL_COMPLETED',
            'payload_json' => json_encode([]),
            'created_at' => now()->subMinutes(5),
        ]);

        $existing = [
            [
                'event' => 'AE_LIVE_EVENT',
                'timestamp' => now()->subMinute()->toIso8601String(),
                'label' => 'From AE3',
                'active' => true,
            ],
        ];

        $service = app(ZoneAutomationObservabilityService::class);
        $payload = $service->enrichPayload($zone->id, [
            'timeline' => $existing,
            'observability' => [
                'runtime' => ['task_is_active' => true],
                'hang_hints' => [],
                'overall_health' => 'active',
            ],
        ]);

        $this->assertSame($existing, $payload['timeline'] ?? null);
    }
}
