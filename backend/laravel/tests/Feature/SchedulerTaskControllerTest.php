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
                'task_id' => 'intent-101',
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
                'task_id' => 'intent-101',
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
                'task_id' => 'intent-202',
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
            ->assertJsonPath('data.0.task_id', 'intent-101')
            ->assertJsonPath('data.0.status', 'completed')
            ->assertJsonPath('data.0.source', 'scheduler_logs');

        $this->assertCount(2, $response->json('data.0.lifecycle'));
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

    public function test_scheduler_task_show_supports_intent_task_ids(): void
    {
        [$user, $token] = $this->createViewer();
        $zone = Zone::factory()->create();

        SchedulerLog::create([
            'task_name' => 'laravel_scheduler_task_irrigation_zone_'.$zone->id,
            'status' => 'accepted',
            'details' => [
                'task_id' => 'intent-77',
                'zone_id' => $zone->id,
                'task_type' => 'irrigation',
                'status' => 'pending',
                'correlation_id' => 'sch:z'.$zone->id.':irrigation:intent-77',
                'created_at' => now()->subMinute()->toIso8601String(),
            ],
        ]);

        SchedulerLog::create([
            'task_name' => 'laravel_scheduler_task_irrigation_zone_'.$zone->id,
            'status' => 'completed',
            'details' => [
                'task_id' => 'intent-77',
                'zone_id' => $zone->id,
                'task_type' => 'irrigation',
                'status' => 'completed',
                'correlation_id' => 'sch:z'.$zone->id.':irrigation:intent-77',
                'updated_at' => now()->toIso8601String(),
            ],
        ]);

        $response = $this->actingAs($user)
            ->withHeader('Authorization', 'Bearer '.$token)
            ->getJson("/api/zones/{$zone->id}/scheduler-tasks/intent-77");

        $response->assertOk()
            ->assertJsonPath('status', 'ok')
            ->assertJsonPath('data.task_id', 'intent-77')
            ->assertJsonPath('data.status', 'completed')
            ->assertJsonCount(2, 'data.lifecycle')
            ->assertJsonPath('data.lifecycle.0.status', 'accepted')
            ->assertJsonPath('data.source', 'scheduler_logs');
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
