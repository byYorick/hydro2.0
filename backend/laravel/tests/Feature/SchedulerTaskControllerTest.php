<?php

namespace Tests\Feature;

use App\Models\SchedulerLog;
use App\Models\User;
use App\Models\Zone;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Schema;
use Tests\RefreshDatabase;
use Tests\TestCase;

class SchedulerTaskControllerTest extends TestCase
{
    use RefreshDatabase;

    public function test_scheduler_tasks_requires_authentication(): void
    {
        $zone = Zone::factory()->create();

        $response = $this->getJson("/api/zones/{$zone->id}/scheduler-tasks");

        $response->assertStatus(401);
    }

    public function test_scheduler_tasks_index_returns_recent_zone_tasks(): void
    {
        [$user, $token] = $this->createViewer();
        $zone = Zone::factory()->create();
        $otherZone = Zone::factory()->create();

        SchedulerLog::create([
            'task_name' => 'laravel_scheduler_task_irrigation_zone_'.$zone->id,
            'status' => 'accepted',
            'details' => [
                'task_id' => '101',
                'zone_id' => $zone->id,
                'task_type' => 'irrigation',
                'status' => 'claimed',
                'created_at' => now()->subMinute()->toIso8601String(),
                'updated_at' => now()->subMinute()->toIso8601String(),
            ],
        ]);

        SchedulerLog::create([
            'task_name' => 'laravel_scheduler_task_irrigation_zone_'.$zone->id,
            'status' => 'completed',
            'details' => [
                'task_id' => '101',
                'zone_id' => $zone->id,
                'task_type' => 'irrigation',
                'status' => 'completed',
                'created_at' => now()->subMinute()->toIso8601String(),
                'updated_at' => now()->toIso8601String(),
            ],
        ]);

        SchedulerLog::create([
            'task_name' => 'laravel_scheduler_task_lighting_zone_'.$otherZone->id,
            'status' => 'completed',
            'details' => [
                'task_id' => '202',
                'zone_id' => $otherZone->id,
                'task_type' => 'lighting',
                'status' => 'completed',
            ],
        ]);

        $response = $this->actingAs($user)
            ->withHeader('Authorization', 'Bearer '.$token)
            ->getJson("/api/zones/{$zone->id}/scheduler-tasks");

        $response->assertOk()
            ->assertJsonPath('status', 'ok')
            ->assertJsonCount(1, 'data')
            ->assertJsonPath('data.0.task_id', '101')
            ->assertJsonPath('data.0.status', 'completed')
            ->assertJsonPath('data.0.source', 'scheduler_logs');

        $this->assertCount(2, $response->json('data.0.lifecycle'));
    }

    public function test_scheduler_tasks_index_omits_legacy_intent_task_ids(): void
    {
        [$user, $token] = $this->createViewer();
        $zone = Zone::factory()->create();

        SchedulerLog::create([
            'task_name' => 'laravel_scheduler_task_irrigation_zone_'.$zone->id,
            'status' => 'completed',
            'details' => [
                'task_id' => 'intent-101',
                'zone_id' => $zone->id,
                'task_type' => 'irrigation',
                'status' => 'completed',
            ],
        ]);

        SchedulerLog::create([
            'task_name' => 'laravel_scheduler_task_irrigation_zone_'.$zone->id,
            'status' => 'completed',
            'details' => [
                'task_id' => '301',
                'zone_id' => $zone->id,
                'task_type' => 'irrigation',
                'status' => 'completed',
            ],
        ]);

        $response = $this->actingAs($user)
            ->withHeader('Authorization', 'Bearer '.$token)
            ->getJson("/api/zones/{$zone->id}/scheduler-tasks");

        $response->assertOk()
            ->assertJsonPath('status', 'ok')
            ->assertJsonCount(1, 'data')
            ->assertJsonPath('data.0.task_id', '301');
    }

    public function test_scheduler_tasks_index_can_include_timeline(): void
    {
        [$user, $token] = $this->createViewer();
        $zone = Zone::factory()->create();

        SchedulerLog::create([
            'task_name' => 'ae_scheduler_task_st-with-timeline',
            'status' => 'completed',
            'details' => [
                'task_id' => 'st-with-timeline',
                'zone_id' => $zone->id,
                'task_type' => 'diagnostics',
                'status' => 'completed',
                'correlation_id' => 'sch:z'.$zone->id.':diagnostics:timeline',
            ],
        ]);

        $payloadColumn = Schema::hasColumn('zone_events', 'payload_json') ? 'payload_json' : 'details';
        DB::table('zone_events')->insert([
            'zone_id' => $zone->id,
            'type' => 'TASK_STARTED',
            $payloadColumn => json_encode([
                'event_id' => 'evt-index-1',
                'event_seq' => 1,
                'event_type' => 'TASK_STARTED',
                'task_id' => 'st-with-timeline',
                'correlation_id' => 'sch:z'.$zone->id.':diagnostics:timeline',
                'task_type' => 'diagnostics',
            ]),
            'created_at' => now()->subSecond(),
        ]);

        $response = $this->actingAs($user)
            ->withHeader('Authorization', 'Bearer '.$token)
            ->getJson("/api/zones/{$zone->id}/scheduler-tasks?include_timeline=1");

        $response->assertOk()
            ->assertJsonPath('status', 'ok')
            ->assertJsonPath('data.0.task_id', 'st-with-timeline')
            ->assertJsonCount(1, 'data.0.timeline')
            ->assertJsonPath('data.0.timeline.0.event_type', 'TASK_STARTED')
            ->assertJsonPath('data.0.process_state.status', 'completed');
    }

    public function test_scheduler_task_show_returns_task_from_scheduler_logs(): void
    {
        [$user, $token] = $this->createViewer();
        $zone = Zone::factory()->create();

        SchedulerLog::create([
            'task_name' => 'ae_scheduler_task_st-done-1',
            'status' => 'completed',
            'details' => [
                'task_id' => 'st-done-1',
                'zone_id' => $zone->id,
                'task_type' => 'irrigation',
                'status' => 'completed',
                'correlation_id' => 'sch:z'.$zone->id.':irrigation:done',
                'result' => [
                    'command_submitted' => true,
                    'command_effect_confirmed' => true,
                    'commands_total' => 1,
                    'commands_effect_confirmed' => 1,
                    'commands_failed' => 0,
                    'executed_steps' => [
                        ['step' => 'irrigation', 'status' => 'completed'],
                    ],
                    'run_mode' => 'run_full',
                ],
            ],
        ]);

        $payloadColumn = Schema::hasColumn('zone_events', 'payload_json') ? 'payload_json' : 'details';
        DB::table('zone_events')->insert([
            'zone_id' => $zone->id,
            'type' => 'TASK_FINISHED',
            $payloadColumn => json_encode([
                'event_id' => 'evt-finish-1',
                'event_seq' => 1,
                'event_type' => 'TASK_FINISHED',
                'task_id' => 'st-done-1',
                'correlation_id' => 'sch:z'.$zone->id.':irrigation:done',
                'task_type' => 'irrigation',
                'reason_code' => 'setup_completed',
            ]),
            'created_at' => now()->subSeconds(2),
        ]);

        $response = $this->actingAs($user)
            ->withHeader('Authorization', 'Bearer '.$token)
            ->getJson("/api/zones/{$zone->id}/scheduler-tasks/st-done-1");

        $response->assertOk()
            ->assertJsonPath('status', 'ok')
            ->assertJsonPath('data.task_id', 'st-done-1')
            ->assertJsonPath('data.status', 'completed')
            ->assertJsonPath('data.source', 'scheduler_logs')
            ->assertJsonPath('data.command_submitted', true)
            ->assertJsonPath('data.command_effect_confirmed', true)
            ->assertJsonPath('data.commands_total', 1)
            ->assertJsonPath('data.commands_effect_confirmed', 1)
            ->assertJsonPath('data.commands_failed', 0)
            ->assertJsonPath('data.executed_steps.0.step', 'irrigation')
            ->assertJsonPath('data.timeline.0.event_type', 'TASK_FINISHED');
    }

    public function test_scheduler_task_show_falls_back_to_scheduler_logs_timeline_when_zone_events_missing(): void
    {
        [$user, $token] = $this->createViewer();
        $zone = Zone::factory()->create();

        SchedulerLog::create([
            'task_name' => 'ae_scheduler_task_st-fallback-1',
            'status' => 'accepted',
            'details' => [
                'task_id' => 'st-fallback-1',
                'zone_id' => $zone->id,
                'task_type' => 'diagnostics',
                'status' => 'accepted',
                'correlation_id' => 'sch:z'.$zone->id.':diagnostics:fallback',
            ],
        ]);

        SchedulerLog::create([
            'task_name' => 'ae_scheduler_task_st-fallback-1',
            'status' => 'failed',
            'details' => [
                'task_id' => 'st-fallback-1',
                'zone_id' => $zone->id,
                'task_type' => 'diagnostics',
                'status' => 'failed',
                'correlation_id' => 'sch:z'.$zone->id.':diagnostics:fallback',
            ],
        ]);

        $response = $this->actingAs($user)
            ->withHeader('Authorization', 'Bearer '.$token)
            ->getJson("/api/zones/{$zone->id}/scheduler-tasks/st-fallback-1");

        $response->assertOk()
            ->assertJsonPath('status', 'ok')
            ->assertJsonPath('data.task_id', 'st-fallback-1')
            ->assertJsonCount(2, 'data.timeline')
            ->assertJsonPath('data.timeline.0.event_type', 'TASK_STARTED')
            ->assertJsonPath('data.timeline.0.source', 'scheduler_logs_fallback')
            ->assertJsonPath('data.timeline.1.event_type', 'SCHEDULE_TASK_FAILED');
    }

    public function test_scheduler_tasks_index_include_timeline_falls_back_to_lifecycle_when_zone_events_missing(): void
    {
        [$user, $token] = $this->createViewer();
        $zone = Zone::factory()->create();

        SchedulerLog::create([
            'task_name' => 'ae_scheduler_task_st-index-fallback',
            'status' => 'accepted',
            'details' => [
                'task_id' => 'st-index-fallback',
                'zone_id' => $zone->id,
                'task_type' => 'diagnostics',
                'status' => 'accepted',
                'correlation_id' => 'sch:z'.$zone->id.':diagnostics:index-fallback',
            ],
        ]);

        SchedulerLog::create([
            'task_name' => 'ae_scheduler_task_st-index-fallback',
            'status' => 'completed',
            'details' => [
                'task_id' => 'st-index-fallback',
                'zone_id' => $zone->id,
                'task_type' => 'diagnostics',
                'status' => 'completed',
                'correlation_id' => 'sch:z'.$zone->id.':diagnostics:index-fallback',
            ],
        ]);

        $response = $this->actingAs($user)
            ->withHeader('Authorization', 'Bearer '.$token)
            ->getJson("/api/zones/{$zone->id}/scheduler-tasks?include_timeline=1");

        $response->assertOk()
            ->assertJsonPath('status', 'ok')
            ->assertJsonPath('data.0.task_id', 'st-index-fallback')
            ->assertJsonCount(2, 'data.0.timeline')
            ->assertJsonPath('data.0.timeline.0.event_type', 'TASK_STARTED')
            ->assertJsonPath('data.0.timeline.0.source', 'scheduler_logs_lifecycle_fallback')
            ->assertJsonPath('data.0.timeline.1.event_type', 'TASK_FINISHED');
    }

    public function test_scheduler_task_show_returns_not_found_when_task_missing(): void
    {
        [$user, $token] = $this->createViewer();
        $zone = Zone::factory()->create();

        $response = $this->actingAs($user)
            ->withHeader('Authorization', 'Bearer '.$token)
            ->getJson("/api/zones/{$zone->id}/scheduler-tasks/st-missing-1");

        $response->assertNotFound()
            ->assertJsonPath('status', 'error')
            ->assertJsonPath('code', 'NOT_FOUND');
    }

    public function test_scheduler_task_show_rejects_legacy_intent_task_ids(): void
    {
        [$user, $token] = $this->createViewer();
        $zone = Zone::factory()->create();

        $response = $this->actingAs($user)
            ->withHeader('Authorization', 'Bearer '.$token)
            ->getJson("/api/zones/{$zone->id}/scheduler-tasks/intent-77");

        $response->assertStatus(422)
            ->assertJsonPath('status', 'error')
            ->assertJsonPath('code', 'VALIDATION_ERROR');
    }

    public function test_scheduler_task_show_supports_numeric_ae3_task_ids(): void
    {
        [$user, $token] = $this->createViewer();
        $zone = Zone::factory()->create(['automation_runtime' => 'ae3']);

        SchedulerLog::create([
            'task_name' => 'laravel_scheduler_task_irrigation_zone_'.$zone->id,
            'status' => 'accepted',
            'details' => [
                'task_id' => '321',
                'zone_id' => $zone->id,
                'task_type' => 'irrigation',
                'status' => 'accepted',
                'correlation_id' => 'sch:z'.$zone->id.':irrigation:321',
            ],
        ]);

        SchedulerLog::create([
            'task_name' => 'laravel_scheduler_task_irrigation_zone_'.$zone->id,
            'status' => 'completed',
            'details' => [
                'task_id' => '321',
                'zone_id' => $zone->id,
                'task_type' => 'irrigation',
                'status' => 'completed',
                'correlation_id' => 'sch:z'.$zone->id.':irrigation:321',
            ],
        ]);

        $response = $this->actingAs($user)
            ->withHeader('Authorization', 'Bearer '.$token)
            ->getJson("/api/zones/{$zone->id}/scheduler-tasks/321");

        $response->assertOk()
            ->assertJsonPath('status', 'ok')
            ->assertJsonPath('data.task_id', '321')
            ->assertJsonPath('data.status', 'completed')
            ->assertJsonCount(2, 'data.lifecycle');
    }

    public function test_scheduler_task_show_builds_process_steps_from_ae_stage_transitions(): void
    {
        [$user, $token] = $this->createViewer();
        $zone = Zone::factory()->create(['automation_runtime' => 'ae3']);
        $now = now();

        $aeTaskId = (int) DB::table('ae_tasks')->insertGetId([
            'zone_id' => $zone->id,
            'task_type' => 'cycle_start',
            'status' => 'completed',
            'idempotency_key' => 'sch:z'.$zone->id.':irrigation:runtime-graph',
            'scheduled_for' => $now->copy()->subMinute(),
            'due_at' => $now->copy()->subSeconds(50),
            'current_stage' => 'complete_ready',
            'workflow_phase' => 'ready',
            'created_at' => $now->copy()->subMinute(),
            'updated_at' => $now->copy()->subSeconds(2),
            'completed_at' => $now->copy()->subSeconds(2),
        ]);

        DB::table('ae_stage_transitions')->insert([
            [
                'task_id' => $aeTaskId,
                'from_stage' => 'startup',
                'to_stage' => 'solution_fill_start',
                'workflow_phase' => 'tank_filling',
                'triggered_at' => $now->copy()->subSeconds(40),
                'metadata' => json_encode([]),
                'created_at' => $now->copy()->subSeconds(40),
            ],
            [
                'task_id' => $aeTaskId,
                'from_stage' => 'solution_fill_start',
                'to_stage' => 'solution_fill_check',
                'workflow_phase' => 'tank_filling',
                'triggered_at' => $now->copy()->subSeconds(30),
                'metadata' => json_encode([]),
                'created_at' => $now->copy()->subSeconds(30),
            ],
            [
                'task_id' => $aeTaskId,
                'from_stage' => 'solution_fill_check',
                'to_stage' => 'solution_fill_stop_to_ready',
                'workflow_phase' => 'ready',
                'triggered_at' => $now->copy()->subSeconds(20),
                'metadata' => json_encode([]),
                'created_at' => $now->copy()->subSeconds(20),
            ],
            [
                'task_id' => $aeTaskId,
                'from_stage' => 'solution_fill_stop_to_ready',
                'to_stage' => 'complete_ready',
                'workflow_phase' => 'ready',
                'triggered_at' => $now->copy()->subSeconds(10),
                'metadata' => json_encode([]),
                'created_at' => $now->copy()->subSeconds(10),
            ],
        ]);

        SchedulerLog::create([
            'task_name' => 'laravel_scheduler_task_irrigation_zone_'.$zone->id,
            'status' => 'completed',
            'details' => [
                'task_id' => (string) $aeTaskId,
                'zone_id' => $zone->id,
                'task_type' => 'irrigation',
                'status' => 'completed',
                'correlation_id' => 'sch:z'.$zone->id.':irrigation:runtime-graph',
            ],
        ]);

        $response = $this->actingAs($user)
            ->withHeader('Authorization', 'Bearer '.$token)
            ->getJson("/api/zones/{$zone->id}/scheduler-tasks/{$aeTaskId}");

        $response->assertOk()
            ->assertJsonPath('data.status', 'completed')
            ->assertJsonPath('data.process_state.status', 'completed')
            ->assertJsonPath('data.process_state.phase', 'setup_transition')
            ->assertJsonPath('data.process_steps.0.status', 'completed')
            ->assertJsonPath('data.process_steps.1.status', 'completed')
            ->assertJsonPath('data.process_steps.2.status', 'pending')
            ->assertJsonPath('data.process_steps.3.status', 'completed');
    }

    public function test_scheduler_task_show_marks_failed_phase_from_ae_current_stage(): void
    {
        [$user, $token] = $this->createViewer();
        $zone = Zone::factory()->create(['automation_runtime' => 'ae3']);
        $now = now();

        $aeTaskId = (int) DB::table('ae_tasks')->insertGetId([
            'zone_id' => $zone->id,
            'task_type' => 'cycle_start',
            'status' => 'failed',
            'idempotency_key' => 'sch:z'.$zone->id.':mist:runtime-failed',
            'scheduled_for' => $now->copy()->subMinute(),
            'due_at' => $now->copy()->subSeconds(55),
            'current_stage' => 'startup',
            'workflow_phase' => 'idle',
            'error_code' => 'two_tank_clean_level_stale',
            'error_message' => 'Clean tank telemetry is stale',
            'created_at' => $now->copy()->subMinute(),
            'updated_at' => $now->copy()->subSeconds(5),
            'completed_at' => $now->copy()->subSeconds(5),
        ]);

        SchedulerLog::create([
            'task_name' => 'laravel_scheduler_task_mist_zone_'.$zone->id,
            'status' => 'failed',
            'details' => [
                'task_id' => (string) $aeTaskId,
                'zone_id' => $zone->id,
                'task_type' => 'mist',
                'status' => 'failed',
                'correlation_id' => 'sch:z'.$zone->id.':mist:runtime-failed',
            ],
        ]);

        $response = $this->actingAs($user)
            ->withHeader('Authorization', 'Bearer '.$token)
            ->getJson("/api/zones/{$zone->id}/scheduler-tasks/{$aeTaskId}");

        $response->assertOk()
            ->assertJsonPath('data.status', 'failed')
            ->assertJsonPath('data.process_state.status', 'failed')
            ->assertJsonPath('data.process_state.phase', 'clean_fill')
            ->assertJsonPath('data.process_steps.0.status', 'failed')
            ->assertJsonPath('data.process_steps.3.status', 'pending');
    }

    public function test_scheduler_task_show_enriches_status_from_active_task_snapshot(): void
    {
        [$user, $token] = $this->createViewer();
        $zone = Zone::factory()->create();
        $now = now();

        SchedulerLog::create([
            'task_name' => 'laravel_scheduler_task_irrigation_zone_'.$zone->id,
            'status' => 'accepted',
            'details' => [
                'task_id' => 'st-active-overlay',
                'zone_id' => $zone->id,
                'task_type' => 'irrigation',
                'status' => 'accepted',
                'correlation_id' => 'sch:z'.$zone->id.':irrigation:active-overlay',
            ],
        ]);

        DB::table('laravel_scheduler_active_tasks')->insert([
            'task_id' => 'st-active-overlay',
            'zone_id' => $zone->id,
            'task_type' => 'irrigation',
            'schedule_key' => 'zone:'.$zone->id.':irrigation',
            'correlation_id' => 'sch:z'.$zone->id.':irrigation:active-overlay',
            'status' => 'completed',
            'accepted_at' => $now->copy()->subSeconds(30),
            'terminal_at' => $now->copy()->subSeconds(5),
            'last_polled_at' => $now->copy()->subSeconds(5),
            'details' => json_encode(['terminal_source' => 'automation_engine_status_poll']),
            'created_at' => $now->copy()->subSeconds(30),
            'updated_at' => $now->copy()->subSeconds(5),
        ]);

        $response = $this->actingAs($user)
            ->withHeader('Authorization', 'Bearer '.$token)
            ->getJson("/api/zones/{$zone->id}/scheduler-tasks/st-active-overlay");

        $response->assertOk()
            ->assertJsonPath('data.status', 'completed')
            ->assertJsonPath('data.process_state.status', 'completed');
    }

    public function test_scheduler_task_show_rejects_invalid_task_id(): void
    {
        [$user, $token] = $this->createViewer();
        $zone = Zone::factory()->create();

        $response = $this->actingAs($user)
            ->withHeader('Authorization', 'Bearer '.$token)
            ->getJson("/api/zones/{$zone->id}/scheduler-tasks/bad");

        $response->assertStatus(422)
            ->assertJsonPath('status', 'error')
            ->assertJsonPath('code', 'VALIDATION_ERROR');
    }

    /**
     * @return array{0: User, 1: string}
     */
    private function createViewer(): array
    {
        $user = User::factory()->create(['role' => 'viewer']);
        $token = $user->createToken('test')->plainTextToken;

        return [$user, $token];
    }
}
