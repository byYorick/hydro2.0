<?php

namespace Tests\Feature;

use App\Models\GrowCycle;
use App\Models\User;
use App\Models\Zone;
use App\Services\EffectiveTargetsService;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Http;
use Illuminate\Support\Facades\Schema;
use Mockery;
use Tests\RefreshDatabase;
use Tests\TestCase;

class ScheduleWorkspaceControllerTest extends TestCase
{
    use RefreshDatabase;

    public function test_schedule_workspace_requires_authentication(): void
    {
        $zone = Zone::factory()->create();

        $response = $this->getJson("/api/zones/{$zone->id}/schedule-workspace");

        $response->assertStatus(401);
    }

    public function test_schedule_workspace_returns_plan_and_execution_from_canonical_sources(): void
    {
        [$user, $token] = $this->createViewer();
        $zone = Zone::factory()->create([
            'automation_runtime' => 'ae3',
        ]);

        $cycle = GrowCycle::factory()->create([
            'zone_id' => $zone->id,
            'status' => 'RUNNING',
        ]);

        $effectiveTargetsService = Mockery::mock(EffectiveTargetsService::class);
        $effectiveTargetsService
            ->shouldReceive('getEffectiveTargetsBatch')
            ->once()
            ->with([$cycle->id])
            ->andReturn([
                $cycle->id => [
                    'targets' => [
                        'irrigation' => [
                            'interval_sec' => 1800,
                        ],
                        'lighting' => [
                            'start_time' => '08:00:00',
                            'photoperiod_hours' => 12,
                        ],
                    ],
                ],
            ]);
        $this->app->instance(EffectiveTargetsService::class, $effectiveTargetsService);

        Http::fake([
            '*' => Http::response([
                'status' => 'ok',
                'data' => [
                    'control_mode' => 'semi',
                    'allowed_manual_steps' => ['clean_fill_start'],
                ],
            ]),
        ]);

        $intentId = DB::table('zone_automation_intents')->insertGetId([
            'zone_id' => $zone->id,
            'intent_type' => 'IRRIGATE_ONCE',
            'payload' => json_encode([
                'source' => 'laravel_scheduler',
                'task_type' => 'irrigation',
                'workflow' => 'cycle_start',
            ], JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES),
            'idempotency_key' => 'sch:z'.$zone->id.':irrigation:test',
            'status' => 'running',
            'created_at' => now(),
            'updated_at' => now(),
        ]);

        $executionId = (int) DB::table('ae_tasks')->insertGetId([
            'zone_id' => $zone->id,
            'task_type' => 'cycle_start',
            'status' => 'running',
            'idempotency_key' => 'sch:z'.$zone->id.':irrigation:test',
            'intent_id' => $intentId,
            'intent_source' => 'laravel_scheduler',
            'intent_meta' => json_encode([], JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES),
            'topology' => 'two_tank',
            'current_stage' => 'startup',
            'workflow_phase' => 'idle',
            'scheduled_for' => now()->subMinute(),
            'due_at' => now()->addMinute(),
            'created_at' => now()->subMinute(),
            'updated_at' => now(),
        ]);

        DB::table('laravel_scheduler_active_tasks')->insert([
            'task_id' => (string) $executionId,
            'zone_id' => $zone->id,
            'task_type' => 'irrigation',
            'schedule_key' => 'zone:'.$zone->id.'|type:irrigation|time=None|start=None|end=None|interval=1800',
            'correlation_id' => 'sch:z'.$zone->id.':irrigation:test',
            'status' => 'running',
            'accepted_at' => now()->subMinute(),
            'due_at' => now()->addMinute(),
            'expires_at' => now()->addMinutes(5),
            'last_polled_at' => now(),
            'details' => json_encode([], JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES),
            'created_at' => now()->subMinute(),
            'updated_at' => now(),
        ]);

        DB::table('zone_automation_intents')->insert([
            'zone_id' => $zone->id,
            'intent_type' => 'IRRIGATE_ONCE',
            'payload' => json_encode([
                'source' => 'laravel_scheduler',
                'task_type' => 'irrigation',
                'workflow' => 'cycle_start',
            ], JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES),
            'idempotency_key' => 'sch:z'.$zone->id.':irrigation:busy',
            'status' => 'failed',
            'error_code' => 'start_cycle_zone_busy',
            'error_message' => 'Intent skipped: zone busy',
            'created_at' => now()->subSeconds(30),
            'updated_at' => now()->subSeconds(30),
            'completed_at' => now()->subSeconds(30),
        ]);

        $response = $this->actingAs($user)
            ->withHeader('Authorization', 'Bearer '.$token)
            ->getJson("/api/zones/{$zone->id}/schedule-workspace?horizon=24h");

        $response->assertOk()
            ->assertJsonPath('status', 'ok')
            ->assertJsonPath('data.control.automation_runtime', 'ae3')
            ->assertJsonPath('data.control.control_mode', 'semi')
            ->assertJsonPath('data.capabilities.executable_task_types.0', 'irrigation')
            ->assertJsonPath('data.capabilities.ae3_irrigation_only_dispatch', true)
            ->assertJsonPath('data.capabilities.non_executable_planned_task_types.0', 'lighting')
            ->assertJsonPath('data.execution.active_run.execution_id', (string) $executionId)
            ->assertJsonPath('data.execution.active_run.task_type', 'irrigation')
            ->assertJsonPath('data.execution.recent_runs.0.execution_id', (string) $executionId)
            ->assertJsonPath('data.execution.counters.active', 1)
            ->assertJsonPath('data.execution.counters.failed_24h', 1)
            ->assertJsonPath('data.execution.latest_failure.error_code', 'start_cycle_zone_busy')
            ->assertJsonPath('data.execution.latest_failure.human_error_message', 'Повторный запуск отклонён: по зоне уже есть активный intent или выполняемая задача.')
            ->assertJsonPath('data.execution.latest_failure.source', 'zone_automation_intents');

        $this->assertContains('irrigation', array_column($response->json('data.plan.lanes'), 'task_type'));
        $this->assertGreaterThan(0, count($response->json('data.plan.windows')));
    }

    public function test_schedule_execution_returns_execution_detail_and_timeline(): void
    {
        [$user, $token] = $this->createViewer();
        $zone = Zone::factory()->create();

        $intentId = DB::table('zone_automation_intents')->insertGetId([
            'zone_id' => $zone->id,
            'intent_type' => 'IRRIGATE_ONCE',
            'payload' => json_encode([
                'source' => 'laravel_scheduler',
                'task_type' => 'irrigation',
                'workflow' => 'cycle_start',
            ], JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES),
            'idempotency_key' => 'sch:z'.$zone->id.':irrigation:detail',
            'status' => 'completed',
            'created_at' => now()->subMinutes(3),
            'updated_at' => now()->subMinute(),
            'completed_at' => now()->subMinute(),
        ]);

        $executionId = (int) DB::table('ae_tasks')->insertGetId([
            'zone_id' => $zone->id,
            'task_type' => 'cycle_start',
            'status' => 'completed',
            'idempotency_key' => 'sch:z'.$zone->id.':irrigation:detail',
            'intent_id' => $intentId,
            'intent_source' => 'laravel_scheduler',
            'intent_meta' => json_encode([], JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES),
            'topology' => 'two_tank',
            'current_stage' => 'startup',
            'workflow_phase' => 'idle',
            'scheduled_for' => now()->subMinutes(3),
            'due_at' => now()->subMinutes(2),
            'completed_at' => now()->subMinute(),
            'created_at' => now()->subMinutes(3),
            'updated_at' => now()->subMinute(),
        ]);

        DB::table('laravel_scheduler_active_tasks')->insert([
            'task_id' => (string) $executionId,
            'zone_id' => $zone->id,
            'task_type' => 'irrigation',
            'schedule_key' => 'zone:'.$zone->id.'|type:irrigation|time=None|start=None|end=None|interval=1800',
            'correlation_id' => 'sch:z'.$zone->id.':irrigation:detail',
            'status' => 'completed',
            'accepted_at' => now()->subMinutes(3),
            'due_at' => now()->subMinutes(2),
            'expires_at' => now()->addMinute(),
            'terminal_at' => now()->subMinute(),
            'details' => json_encode([], JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES),
            'created_at' => now()->subMinutes(3),
            'updated_at' => now()->subMinute(),
        ]);

        $payloadColumn = Schema::hasColumn('zone_events', 'payload_json') ? 'payload_json' : 'details';
        DB::table('zone_events')->insert([
            [
                'zone_id' => $zone->id,
                'type' => 'AE_TASK_STARTED',
                $payloadColumn => json_encode([
                    'event_id' => 'evt-execution-0',
                    'event_seq' => 0,
                    'event_type' => 'AE_TASK_STARTED',
                    'task_id' => (string) $executionId,
                    'correlation_id' => 'sch:z'.$zone->id.':irrigation:detail',
                    'task_type' => 'irrigation',
                    'stage' => 'prepare_recirculation_check',
                ], JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES),
                'created_at' => now()->subMinutes(2),
            ],
            [
                'zone_id' => $zone->id,
                'type' => 'TASK_FINISHED',
                $payloadColumn => json_encode([
                    'event_id' => 'evt-execution-1',
                    'event_seq' => 1,
                    'event_type' => 'TASK_FINISHED',
                    'task_id' => (string) $executionId,
                    'correlation_id' => 'sch:z'.$zone->id.':irrigation:detail',
                    'task_type' => 'irrigation',
                    'reason_code' => 'setup_completed',
                ], JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES),
                'created_at' => now()->subMinute(),
            ],
        ]);

        $response = $this->actingAs($user)
            ->withHeader('Authorization', 'Bearer '.$token)
            ->getJson("/api/zones/{$zone->id}/executions/{$executionId}");

        $response->assertOk()
            ->assertJsonPath('status', 'ok')
            ->assertJsonPath('data.execution_id', (string) $executionId)
            ->assertJsonPath('data.task_type', 'irrigation')
            ->assertJsonPath('data.status', 'completed')
            ->assertJsonPath('data.timeline.0.event_type', 'AE_TASK_STARTED')
            ->assertJsonPath('data.timeline.0.stage', 'prepare_recirculation_check')
            ->assertJsonPath('data.timeline.1.event_type', 'TASK_FINISHED')
            ->assertJsonPath('data.timeline.1.reason_code', 'setup_completed');
    }

    public function test_scheduler_diagnostics_is_forbidden_for_viewer(): void
    {
        [$user, $token] = $this->createViewer();
        $zone = Zone::factory()->create();

        $response = $this->actingAs($user)
            ->withHeader('Authorization', 'Bearer '.$token)
            ->getJson("/api/zones/{$zone->id}/scheduler-diagnostics");

        $response->assertForbidden();
    }

    public function test_scheduler_diagnostics_returns_dispatcher_state_and_recent_logs_for_engineer(): void
    {
        [$user, $token] = $this->createEngineer();
        $zone = Zone::factory()->create();
        $foreignZone = Zone::factory()->create();

        DB::table('laravel_scheduler_active_tasks')->insert([
            'task_id' => 'diag-401',
            'zone_id' => $zone->id,
            'task_type' => 'irrigation',
            'schedule_key' => 'zone:'.$zone->id.'|type:irrigation|interval=1800',
            'correlation_id' => 'sch:z'.$zone->id.':diag:1',
            'status' => 'running',
            'accepted_at' => now()->subMinutes(5),
            'due_at' => now()->subMinute(),
            'expires_at' => now()->addMinute(),
            'last_polled_at' => now()->subSeconds(10),
            'details' => json_encode(['intent_id' => 10], JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES),
            'created_at' => now()->subMinutes(5),
            'updated_at' => now(),
        ]);

        DB::table('laravel_scheduler_active_tasks')->insert([
            'task_id' => 'diag-foreign',
            'zone_id' => $foreignZone->id,
            'task_type' => 'lighting',
            'schedule_key' => 'zone:'.$foreignZone->id.'|type:lighting|time=08:00:00',
            'correlation_id' => 'sch:z'.$foreignZone->id.':diag:1',
            'status' => 'completed',
            'accepted_at' => now()->subMinutes(10),
            'due_at' => now()->subMinutes(9),
            'expires_at' => now()->subMinutes(8),
            'last_polled_at' => now()->subMinutes(8),
            'terminal_at' => now()->subMinutes(8),
            'details' => json_encode([], JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES),
            'created_at' => now()->subMinutes(10),
            'updated_at' => now()->subMinutes(8),
        ]);

        DB::table('scheduler_logs')->insert([
            [
                'task_name' => 'laravel_scheduler_task_irrigation_zone_'.$zone->id,
                'status' => 'running',
                'details' => json_encode([
                    'zone_id' => (string) $zone->id,
                    'task_id' => 'diag-401',
                ], JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES),
                'created_at' => now()->subSeconds(30),
            ],
            [
                'task_name' => 'laravel_scheduler_task_lighting_zone_'.$foreignZone->id,
                'status' => 'completed',
                'details' => json_encode([
                    'zone_id' => (string) $foreignZone->id,
                    'task_id' => 'diag-foreign',
                ], JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES),
                'created_at' => now()->subMinute(),
            ],
        ]);

        $response = $this->actingAs($user)
            ->withHeader('Authorization', 'Bearer '.$token)
            ->getJson("/api/zones/{$zone->id}/scheduler-diagnostics");

        $response->assertOk()
            ->assertJsonPath('status', 'ok')
            ->assertJsonPath('data.zone_id', $zone->id)
            ->assertJsonPath('data.sources.dispatcher_tasks', true)
            ->assertJsonPath('data.sources.scheduler_logs', true)
            ->assertJsonPath('data.summary.tracked_tasks_total', 1)
            ->assertJsonPath('data.summary.active_tasks_total', 1)
            ->assertJsonPath('data.summary.overdue_tasks_total', 1)
            ->assertJsonPath('data.summary.recent_logs_total', 1)
            ->assertJsonPath('data.dispatcher_tasks.0.task_id', 'diag-401')
            ->assertJsonPath('data.dispatcher_tasks.0.status', 'running')
            ->assertJsonPath('data.recent_logs.0.task_name', 'laravel_scheduler_task_irrigation_zone_'.$zone->id)
            ->assertJsonPath('data.recent_logs.0.status', 'running');
    }

    private function createViewer(): array
    {
        $user = User::factory()->create(['role' => 'viewer']);
        $token = $user->createToken('test')->plainTextToken;

        return [$user, $token];
    }

    private function createEngineer(): array
    {
        $user = User::factory()->create(['role' => 'engineer']);
        $token = $user->createToken('test')->plainTextToken;

        return [$user, $token];
    }
}
