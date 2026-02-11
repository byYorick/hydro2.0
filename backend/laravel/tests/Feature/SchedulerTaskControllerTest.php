<?php

namespace Tests\Feature;

use App\Models\SchedulerLog;
use App\Models\User;
use App\Models\Zone;
use Illuminate\Support\Facades\Http;
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
        $user = User::factory()->create(['role' => 'viewer']);
        $token = $user->createToken('test')->plainTextToken;

        $zone = Zone::factory()->create();
        $otherZone = Zone::factory()->create();

        SchedulerLog::create([
            'task_name' => 'ae_scheduler_task_st-abc',
            'status' => 'accepted',
            'details' => [
                'task_id' => 'st-abc',
                'zone_id' => $zone->id,
                'task_type' => 'irrigation',
                'status' => 'accepted',
                'created_at' => now()->subMinute()->toIso8601String(),
                'updated_at' => now()->subMinute()->toIso8601String(),
            ],
        ]);

        SchedulerLog::create([
            'task_name' => 'ae_scheduler_task_st-abc',
            'status' => 'completed',
            'details' => [
                'task_id' => 'st-abc',
                'zone_id' => $zone->id,
                'task_type' => 'irrigation',
                'status' => 'completed',
                'created_at' => now()->subMinute()->toIso8601String(),
                'updated_at' => now()->toIso8601String(),
            ],
        ]);

        SchedulerLog::create([
            'task_name' => 'ae_scheduler_task_st-other',
            'status' => 'completed',
            'details' => [
                'task_id' => 'st-other',
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
            ->assertJsonPath('data.0.task_id', 'st-abc')
            ->assertJsonPath('data.0.status', 'completed');

        $this->assertCount(2, $response->json('data.0.lifecycle'));
    }

    public function test_scheduler_tasks_index_orders_lifecycle_deterministically_when_timestamps_match(): void
    {
        $user = User::factory()->create(['role' => 'viewer']);
        $token = $user->createToken('test')->plainTextToken;
        $zone = Zone::factory()->create();
        $sameTimestamp = now()->subMinute()->startOfSecond();

        SchedulerLog::create([
            'task_name' => 'ae_scheduler_task_st-same-time',
            'status' => 'accepted',
            'details' => [
                'task_id' => 'st-same-time',
                'zone_id' => $zone->id,
                'task_type' => 'irrigation',
                'status' => 'accepted',
                'created_at' => $sameTimestamp->toIso8601String(),
                'updated_at' => $sameTimestamp->toIso8601String(),
            ],
            'created_at' => $sameTimestamp,
            'updated_at' => $sameTimestamp,
        ]);

        SchedulerLog::create([
            'task_name' => 'ae_scheduler_task_st-same-time',
            'status' => 'completed',
            'details' => [
                'task_id' => 'st-same-time',
                'zone_id' => $zone->id,
                'task_type' => 'irrigation',
                'status' => 'completed',
                'created_at' => $sameTimestamp->toIso8601String(),
                'updated_at' => $sameTimestamp->toIso8601String(),
            ],
            'created_at' => $sameTimestamp,
            'updated_at' => $sameTimestamp,
        ]);

        $response = $this->actingAs($user)
            ->withHeader('Authorization', 'Bearer '.$token)
            ->getJson("/api/zones/{$zone->id}/scheduler-tasks");

        $response->assertOk()
            ->assertJsonPath('status', 'ok')
            ->assertJsonPath('data.0.task_id', 'st-same-time')
            ->assertJsonPath('data.0.status', 'completed');

        $statuses = array_column($response->json('data.0.lifecycle') ?? [], 'status');
        $this->assertSame(['accepted', 'completed'], $statuses);
    }

    public function test_scheduler_task_show_prefers_automation_engine_status(): void
    {
        $user = User::factory()->create(['role' => 'viewer']);
        $token = $user->createToken('test')->plainTextToken;
        $zone = Zone::factory()->create();

        SchedulerLog::create([
            'task_name' => 'ae_scheduler_task_st-live01',
            'status' => 'accepted',
            'details' => [
                'task_id' => 'st-live01',
                'zone_id' => $zone->id,
                'task_type' => 'lighting',
                'status' => 'accepted',
            ],
        ]);

        Http::fake([
            'http://automation-engine:9405/scheduler/task/st-live01' => Http::response([
                'status' => 'ok',
                'data' => [
                    'task_id' => 'st-live01',
                    'zone_id' => $zone->id,
                    'task_type' => 'lighting',
                    'status' => 'running',
                    'created_at' => now()->subMinute()->toIso8601String(),
                    'updated_at' => now()->toIso8601String(),
                    'scheduled_for' => null,
                    'due_at' => now()->addSeconds(30)->toIso8601String(),
                    'expires_at' => now()->addMinutes(2)->toIso8601String(),
                    'correlation_id' => null,
                    'result' => null,
                    'error' => null,
                ],
            ], 200),
        ]);

        $response = $this->actingAs($user)
            ->withHeader('Authorization', 'Bearer '.$token)
            ->getJson("/api/zones/{$zone->id}/scheduler-tasks/st-live01");

        $response->assertOk()
            ->assertJsonPath('status', 'ok')
            ->assertJsonPath('data.task_id', 'st-live01')
            ->assertJsonPath('data.status', 'running')
            ->assertJsonPath('data.source', 'automation_engine');

        $this->assertNotNull($response->json('data.due_at'));
        $this->assertNotNull($response->json('data.expires_at'));
    }

    public function test_scheduler_tasks_index_can_include_timeline(): void
    {
        $user = User::factory()->create(['role' => 'viewer']);
        $token = $user->createToken('test')->plainTextToken;
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
            ->assertJsonPath('data.0.timeline.0.event_type', 'TASK_STARTED');
    }

    public function test_scheduler_task_show_returns_not_found_when_automation_missing_even_if_scheduler_log_exists(): void
    {
        $user = User::factory()->create(['role' => 'viewer']);
        $token = $user->createToken('test')->plainTextToken;
        $zone = Zone::factory()->create();

        SchedulerLog::create([
            'task_name' => 'ae_scheduler_task_st-fallback',
            'status' => 'completed',
            'details' => [
                'task_id' => 'st-fallback',
                'zone_id' => $zone->id,
                'task_type' => 'diagnostics',
                'status' => 'completed',
                'created_at' => now()->subMinute()->toIso8601String(),
                'updated_at' => now()->toIso8601String(),
            ],
        ]);

        Http::fake([
            'http://automation-engine:9405/scheduler/task/st-fallback' => Http::response([
                'status' => 'error',
                'message' => 'not found',
            ], 404),
        ]);

        $response = $this->actingAs($user)
            ->withHeader('Authorization', 'Bearer '.$token)
            ->getJson("/api/zones/{$zone->id}/scheduler-tasks/st-fallback");

        $response->assertNotFound()
            ->assertJsonPath('status', 'error')
            ->assertJsonPath('code', 'NOT_FOUND');
    }

    public function test_scheduler_task_show_returns_upstream_error_for_unexpected_automation_exception(): void
    {
        $user = User::factory()->create(['role' => 'viewer']);
        $token = $user->createToken('test')->plainTextToken;
        $zone = Zone::factory()->create();

        Http::fake([
            'http://automation-engine:9405/scheduler/task/st-upstream-error' => static function () {
                throw new \RuntimeException('malformed upstream payload');
            },
        ]);

        $response = $this->actingAs($user)
            ->withHeader('Authorization', 'Bearer '.$token)
            ->getJson("/api/zones/{$zone->id}/scheduler-tasks/st-upstream-error");

        $response->assertStatus(503)
            ->assertJsonPath('status', 'error')
            ->assertJsonPath('code', 'UPSTREAM_ERROR');
    }

    public function test_scheduler_task_show_returns_upstream_error_when_automation_returns_non_ok_payload(): void
    {
        $user = User::factory()->create(['role' => 'viewer']);
        $token = $user->createToken('test')->plainTextToken;
        $zone = Zone::factory()->create();

        Http::fake([
            'http://automation-engine:9405/scheduler/task/st-upstream-non-ok' => Http::response([
                'status' => 'error',
                'code' => 'TASK_STATUS_UNAVAILABLE',
                'message' => 'temporary degradation',
            ], 200),
        ]);

        $response = $this->actingAs($user)
            ->withHeader('Authorization', 'Bearer '.$token)
            ->getJson("/api/zones/{$zone->id}/scheduler-tasks/st-upstream-non-ok");

        $response->assertStatus(503)
            ->assertJsonPath('status', 'error')
            ->assertJsonPath('code', 'UPSTREAM_ERROR');
    }

    public function test_scheduler_task_show_returns_timeline_events_from_zone_events(): void
    {
        $user = User::factory()->create(['role' => 'viewer']);
        $token = $user->createToken('test')->plainTextToken;
        $zone = Zone::factory()->create();

        SchedulerLog::create([
            'task_name' => 'ae_scheduler_task_st-timeline',
            'status' => 'completed',
            'details' => [
                'task_id' => 'st-timeline',
                'zone_id' => $zone->id,
                'task_type' => 'irrigation',
                'status' => 'completed',
                'correlation_id' => 'sch:z'.$zone->id.':irrigation:timeline',
                'result' => [
                    'action_required' => false,
                    'decision' => 'skip',
                    'reason_code' => 'irrigation_not_required',
                    'reason' => 'Влажность в норме',
                ],
            ],
        ]);

        $payloadColumn = Schema::hasColumn('zone_events', 'payload_json') ? 'payload_json' : 'details';

        DB::table('zone_events')->insert([
            'zone_id' => $zone->id,
            'type' => 'TASK_STARTED',
            $payloadColumn => json_encode([
                'event_id' => 'evt-1',
                'event_seq' => 1,
                'event_type' => 'TASK_STARTED',
                'task_id' => 'st-timeline',
                'correlation_id' => 'sch:z'.$zone->id.':irrigation:timeline',
                'task_type' => 'irrigation',
            ]),
            'created_at' => now()->subSeconds(10),
        ]);

        DB::table('zone_events')->insert([
            'zone_id' => $zone->id,
            'type' => 'DECISION_MADE',
            $payloadColumn => json_encode([
                'event_id' => 'evt-2',
                'event_seq' => 2,
                'event_type' => 'DECISION_MADE',
                'task_id' => 'st-timeline',
                'correlation_id' => 'sch:z'.$zone->id.':irrigation:timeline',
                'task_type' => 'irrigation',
                'action_required' => false,
                'decision' => 'skip',
                'reason_code' => 'irrigation_not_required',
                'reason' => 'Влажность в норме',
            ]),
            'created_at' => now()->subSeconds(5),
        ]);

        Http::fake([
            'http://automation-engine:9405/scheduler/task/st-timeline' => Http::response([
                'status' => 'ok',
                'data' => [
                    'task_id' => 'st-timeline',
                    'zone_id' => $zone->id,
                    'task_type' => 'irrigation',
                    'status' => 'completed',
                    'correlation_id' => 'sch:z'.$zone->id.':irrigation:timeline',
                    'result' => [
                        'action_required' => false,
                        'decision' => 'skip',
                        'reason_code' => 'irrigation_not_required',
                        'reason' => 'Влажность в норме',
                    ],
                ],
            ], 200),
        ]);

        $response = $this->actingAs($user)
            ->withHeader('Authorization', 'Bearer '.$token)
            ->getJson("/api/zones/{$zone->id}/scheduler-tasks/st-timeline");

        $response->assertOk()
            ->assertJsonPath('status', 'ok')
            ->assertJsonPath('data.task_id', 'st-timeline')
            ->assertJsonPath('data.decision', 'skip')
            ->assertJsonPath('data.reason_code', 'irrigation_not_required')
            ->assertJsonCount(2, 'data.timeline')
            ->assertJsonPath('data.timeline.0.event_type', 'TASK_STARTED')
            ->assertJsonPath('data.timeline.1.event_type', 'DECISION_MADE')
            ->assertJsonPath('data.timeline.1.reason_code', 'irrigation_not_required');
    }

    public function test_scheduler_task_timeline_falls_back_to_result_fields_when_root_fields_missing(): void
    {
        $user = User::factory()->create(['role' => 'viewer']);
        $token = $user->createToken('test')->plainTextToken;
        $zone = Zone::factory()->create();

        SchedulerLog::create([
            'task_name' => 'ae_scheduler_task_st-result-timeline',
            'status' => 'failed',
            'details' => [
                'task_id' => 'st-result-timeline',
                'zone_id' => $zone->id,
                'task_type' => 'diagnostics',
                'status' => 'failed',
                'correlation_id' => 'sch:z'.$zone->id.':diagnostics:result',
            ],
        ]);

        $payloadColumn = Schema::hasColumn('zone_events', 'payload_json') ? 'payload_json' : 'details';

        DB::table('zone_events')->insert([
            'zone_id' => $zone->id,
            'type' => 'TASK_FINISHED',
            $payloadColumn => json_encode([
                'event_id' => 'evt-result-1',
                'event_seq' => 1,
                'event_type' => 'TASK_FINISHED',
                'task_id' => 'st-result-timeline',
                'correlation_id' => 'sch:z'.$zone->id.':diagnostics:result',
                'task_type' => 'diagnostics',
                'result' => [
                    'action_required' => true,
                    'decision' => 'execute',
                    'reason_code' => 'execution_exception',
                    'reason' => 'Исключение во время исполнения',
                    'error_code' => 'execution_exception',
                ],
            ]),
            'created_at' => now()->subSeconds(3),
        ]);

        Http::fake([
            'http://automation-engine:9405/scheduler/task/st-result-timeline' => Http::response([
                'status' => 'ok',
                'data' => [
                    'task_id' => 'st-result-timeline',
                    'zone_id' => $zone->id,
                    'task_type' => 'diagnostics',
                    'status' => 'failed',
                    'correlation_id' => 'sch:z'.$zone->id.':diagnostics:result',
                    'error_code' => 'execution_exception',
                    'result' => [
                        'action_required' => true,
                        'decision' => 'execute',
                        'reason_code' => 'execution_exception',
                        'reason' => 'Исключение во время исполнения',
                        'error_code' => 'execution_exception',
                    ],
                ],
            ], 200),
        ]);

        $response = $this->actingAs($user)
            ->withHeader('Authorization', 'Bearer '.$token)
            ->getJson("/api/zones/{$zone->id}/scheduler-tasks/st-result-timeline");

        $response->assertOk()
            ->assertJsonPath('status', 'ok')
            ->assertJsonCount(1, 'data.timeline')
            ->assertJsonPath('data.timeline.0.event_type', 'TASK_FINISHED')
            ->assertJsonPath('data.timeline.0.action_required', true)
            ->assertJsonPath('data.timeline.0.decision', 'execute')
            ->assertJsonPath('data.timeline.0.reason_code', 'execution_exception')
            ->assertJsonPath('data.timeline.0.error_code', 'execution_exception');
    }

    public function test_scheduler_task_show_includes_command_effect_confirmation_fields(): void
    {
        $user = User::factory()->create(['role' => 'viewer']);
        $token = $user->createToken('test')->plainTextToken;
        $zone = Zone::factory()->create();

        Http::fake([
            'http://automation-engine:9405/scheduler/task/st-done-1' => Http::response([
                'status' => 'ok',
                'data' => [
                    'task_id' => 'st-done-1',
                    'zone_id' => $zone->id,
                    'task_type' => 'irrigation',
                    'status' => 'completed',
                    'created_at' => now()->subMinute()->toIso8601String(),
                    'updated_at' => now()->toIso8601String(),
                    'scheduled_for' => now()->subMinute()->toIso8601String(),
                    'due_at' => now()->addSeconds(30)->toIso8601String(),
                    'expires_at' => now()->addMinutes(2)->toIso8601String(),
                    'correlation_id' => 'sch:z'.$zone->id.':irrigation:done',
                    'result' => [
                        'success' => true,
                        'command_submitted' => true,
                        'command_effect_confirmed' => true,
                        'commands_total' => 1,
                        'commands_effect_confirmed' => 1,
                        'commands_failed' => 0,
                    ],
                ],
            ], 200),
        ]);

        $response = $this->actingAs($user)
            ->withHeader('Authorization', 'Bearer '.$token)
            ->getJson("/api/zones/{$zone->id}/scheduler-tasks/st-done-1");

        $response->assertOk()
            ->assertJsonPath('status', 'ok')
            ->assertJsonPath('data.command_submitted', true)
            ->assertJsonPath('data.command_effect_confirmed', true)
            ->assertJsonPath('data.commands_total', 1)
            ->assertJsonPath('data.commands_effect_confirmed', 1)
            ->assertJsonPath('data.commands_failed', 0);
    }
}
