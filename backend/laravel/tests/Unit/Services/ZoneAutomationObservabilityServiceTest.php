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

        DB::table('ae_tasks')->insert([
            'zone_id' => $zone->id,
            'task_type' => 'cycle_start',
            'status' => 'pending',
            'idempotency_key' => $key,
            'scheduled_for' => now(),
            'due_at' => now(),
            'created_at' => now()->subMinutes(5),
            'updated_at' => now()->subMinutes(2),
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
}
