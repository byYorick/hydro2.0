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

    public function test_scheduler_task_show_falls_back_to_scheduler_logs_when_automation_missing(): void
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

        $response->assertOk()
            ->assertJsonPath('status', 'ok')
            ->assertJsonPath('data.task_id', 'st-fallback')
            ->assertJsonPath('data.status', 'completed')
            ->assertJsonPath('data.source', 'scheduler_logs');
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
                'status' => 'error',
                'message' => 'not found',
            ], 404),
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
}
