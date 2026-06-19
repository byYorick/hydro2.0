<?php

namespace Tests\Unit\Services\AutomationScheduler;

use App\Models\LaravelSchedulerActiveTask;
use App\Models\Zone;
use App\Services\AutomationScheduler\ActiveTaskStore;
use Carbon\CarbonImmutable;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Tests\TestCase;

class ActiveTaskStoreTest extends TestCase
{
    use RefreshDatabase;
    public function test_find_latest_terminal_matches_scheduled_run_at_only(): void
    {
        $zone = Zone::factory()->create();
        $zoneId = (int) $zone->id;
        $scheduleKey = "zone:{$zoneId}|manual:9";
        $runAt = '2026-06-20T12:00:00Z';

        LaravelSchedulerActiveTask::query()->create([
            'task_id' => 'old-task',
            'zone_id' => $zoneId,
            'task_type' => 'lighting',
            'schedule_key' => $scheduleKey,
            'correlation_id' => 'corr-old',
            'status' => 'completed',
            'accepted_at' => CarbonImmutable::parse('2026-06-19T12:00:00Z', 'UTC'),
            'terminal_at' => CarbonImmutable::parse('2026-06-19T12:05:00Z', 'UTC'),
            'details' => ['scheduled_for' => '2026-06-19T12:00:00Z'],
        ]);

        LaravelSchedulerActiveTask::query()->create([
            'task_id' => 'new-task',
            'zone_id' => $zoneId,
            'task_type' => 'lighting',
            'schedule_key' => $scheduleKey,
            'correlation_id' => 'corr-new',
            'status' => 'completed',
            'accepted_at' => CarbonImmutable::parse('2026-06-20T12:00:00Z', 'UTC'),
            'terminal_at' => CarbonImmutable::parse('2026-06-20T12:05:00Z', 'UTC'),
            'details' => ['scheduled_for' => $runAt],
        ]);

        $store = new ActiveTaskStore;

        $this->assertNull($store->findLatestTerminalByScheduleKeyForScheduledRunAt($scheduleKey, '2026-06-21T12:00:00Z'));
        $matched = $store->findLatestTerminalByScheduleKeyForScheduledRunAt($scheduleKey, $runAt);
        $this->assertInstanceOf(LaravelSchedulerActiveTask::class, $matched);
        $this->assertSame('new-task', $matched->task_id);
    }
}
