<?php

declare(strict_types=1);

namespace Tests\Feature\Scheduler;

use App\Models\User;
use App\Models\Zone;
use Illuminate\Support\Facades\DB;
use Tests\RefreshDatabase;
use Tests\TestCase;

class ScheduleExecutionRetryTest extends TestCase
{
    use RefreshDatabase;

    private Zone $zone;

    private User $user;

    protected function setUp(): void
    {
        parent::setUp();
        $this->zone = Zone::factory()->create();
        $this->user = User::factory()->create(['role' => 'operator']);
    }

    public function test_retry_requires_authentication(): void
    {
        $response = $this->postJson("/api/zones/{$this->zone->id}/executions/1/retry");
        $response->assertStatus(401);
    }

    public function test_retry_forbidden_for_viewer(): void
    {
        $viewer = User::factory()->create(['role' => 'viewer']);
        $response = $this->actingAs($viewer)
            ->postJson("/api/zones/{$this->zone->id}/executions/1/retry");
        $response->assertStatus(403);
    }

    public function test_retry_rejects_invalid_execution_id(): void
    {
        $response = $this->actingAs($this->user)
            ->postJson("/api/zones/{$this->zone->id}/executions/abc/retry");
        $response->assertStatus(422);
    }

    public function test_retry_returns_404_for_unknown_execution(): void
    {
        $response = $this->actingAs($this->user)
            ->postJson("/api/zones/{$this->zone->id}/executions/999999/retry");
        $response->assertStatus(404);
    }

    public function test_retry_rejects_active_execution(): void
    {
        $taskId = $this->insertTask(['status' => 'running']);
        $response = $this->actingAs($this->user)
            ->postJson("/api/zones/{$this->zone->id}/executions/{$taskId}/retry");
        $response->assertStatus(409);
        $response->assertJsonPath('code', 'INVALID_STATE');
    }

    public function test_retry_rejects_completed_execution(): void
    {
        $taskId = $this->insertTask(['status' => 'completed', 'completed_at' => now()]);
        $response = $this->actingAs($this->user)
            ->postJson("/api/zones/{$this->zone->id}/executions/{$taskId}/retry");
        $response->assertStatus(409);
    }

    public function test_retry_rejects_unsupported_task_type(): void
    {
        $taskId = $this->insertTask([
            'status' => 'failed',
            'task_type' => 'lighting_tick',
            'completed_at' => now(),
        ]);
        $response = $this->actingAs($this->user)
            ->postJson("/api/zones/{$this->zone->id}/executions/{$taskId}/retry");
        $response->assertStatus(422);
        $response->assertJsonPath('code', 'UNSUPPORTED_TASK_TYPE');
    }

    public function test_retry_creates_intent_for_failed_irrigation(): void
    {
        $taskId = $this->insertTask([
            'status' => 'failed',
            'completed_at' => now(),
            'irrigation_mode' => 'normal',
            'irrigation_requested_duration_sec' => 120,
        ]);

        $response = $this->actingAs($this->user)
            ->postJson("/api/zones/{$this->zone->id}/executions/{$taskId}/retry");

        $response->assertStatus(201);
        $response->assertJsonPath('status', 'ok');
        $response->assertJsonPath('data.retry_of_execution_id', (string) $taskId);

        $intentId = $response->json('data.intent_id');
        self::assertIsInt($intentId);

        $this->assertDatabaseHas('zone_automation_intents', [
            'id' => $intentId,
            'zone_id' => $this->zone->id,
            'intent_type' => 'IRRIGATE_ONCE',
            'task_type' => 'irrigation_start',
            'status' => 'pending',
            'intent_source' => 'scheduler_cockpit_retry',
        ]);
    }

    /**
     * @param  array<string, mixed>  $overrides
     */
    private function insertTask(array $overrides = []): int
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

        return (int) DB::table('ae_tasks')->insertGetId(array_merge($base, $overrides));
    }
}
