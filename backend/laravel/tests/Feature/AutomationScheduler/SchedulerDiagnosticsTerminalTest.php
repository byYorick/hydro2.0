<?php

namespace Tests\Feature\AutomationScheduler;

use App\Models\LaravelSchedulerActiveTask;
use App\Models\User;
use App\Models\Zone;
use Tests\RefreshDatabase;
use Tests\TestCase;

class SchedulerDiagnosticsTerminalTest extends TestCase
{
    use RefreshDatabase;

    public function test_terminal_rows_without_terminal_timestamp_are_not_reported_as_overdue(): void
    {
        $zone = Zone::factory()->create();
        LaravelSchedulerActiveTask::create([
            'zone_id' => $zone->id, 'task_id' => 'terminal-fixture', 'task_type' => 'irrigation',
            'schedule_key' => 'terminal-fixture', 'correlation_id' => 'terminal-fixture',
            'accepted_at' => now()->subHours(2), 'status' => 'completed', 'due_at' => now()->subHour(), 'expires_at' => now()->subHour(), 'terminal_at' => null,
        ]);
        $this->actingAs(User::factory()->create(['role' => 'engineer']))
            ->getJson("/api/zones/{$zone->id}/scheduler-diagnostics")
            ->assertOk()->assertJsonPath('data.summary.active_tasks_total', 0)
            ->assertJsonPath('data.summary.overdue_tasks_total', 0)->assertJsonPath('data.summary.stale_tasks_total', 0);
    }
}
