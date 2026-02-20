<?php

namespace Tests\Unit\Services\AutomationScheduler;

use App\Models\Zone;
use App\Services\AutomationScheduler\ActiveTaskStore;
use Carbon\CarbonImmutable;
use Illuminate\Support\Facades\DB;
use Tests\RefreshDatabase;
use Tests\TestCase;

class ActiveTaskStoreTest extends TestCase
{
    use RefreshDatabase;

    private ActiveTaskStore $store;

    protected function setUp(): void
    {
        parent::setUp();
        $this->store = new ActiveTaskStore;
    }

    public function test_upsert_and_find_by_task_id(): void
    {
        $zone = Zone::factory()->create();
        $acceptedAt = CarbonImmutable::parse('2026-02-20 12:00:00', 'UTC');
        $dueAt = $acceptedAt->addSeconds(15);
        $expiresAt = $acceptedAt->addSeconds(120);

        $saved = $this->store->upsertTaskSnapshot(
            taskId: 'task-001',
            zoneId: $zone->id,
            taskType: 'irrigation',
            scheduleKey: 'zone:'.$zone->id.'|type:irrigation|time=12:00:00',
            correlationId: 'sch:z'.$zone->id.':irrigation:abc',
            status: 'accepted',
            acceptedAt: $acceptedAt,
            dueAt: $dueAt,
            expiresAt: $expiresAt,
            details: ['source' => 'unit-test'],
        );

        $this->assertNotNull($saved);
        $this->assertDatabaseHas('laravel_scheduler_active_tasks', [
            'task_id' => 'task-001',
            'zone_id' => $zone->id,
            'status' => 'accepted',
        ]);

        $loaded = $this->store->findByTaskId('task-001');
        $this->assertNotNull($loaded);
        $this->assertSame('task-001', $loaded->task_id);
        $this->assertSame('accepted', $loaded->status);
        $this->assertSame('unit-test', $loaded->details['source'] ?? null);
    }

    public function test_find_active_by_schedule_key_ignores_terminal_and_expired_tasks(): void
    {
        $zone = Zone::factory()->create();
        $now = CarbonImmutable::parse('2026-02-20 12:30:00', 'UTC');
        $scheduleKey = 'zone:'.$zone->id.'|type:lighting|time=12:30:00';

        $this->store->upsertTaskSnapshot(
            taskId: 'task-terminal',
            zoneId: $zone->id,
            taskType: 'lighting',
            scheduleKey: $scheduleKey,
            correlationId: 'corr-terminal',
            status: 'completed',
            acceptedAt: $now->subMinute(),
            dueAt: $now->subSeconds(30),
            expiresAt: $now->addMinute(),
            details: [],
        );

        $this->store->upsertTaskSnapshot(
            taskId: 'task-expired',
            zoneId: $zone->id,
            taskType: 'lighting',
            scheduleKey: $scheduleKey,
            correlationId: 'corr-expired',
            status: 'running',
            acceptedAt: $now->subMinute(),
            dueAt: $now->subSeconds(30),
            expiresAt: $now->subSecond(),
            details: [],
        );

        $this->store->upsertTaskSnapshot(
            taskId: 'task-active',
            zoneId: $zone->id,
            taskType: 'lighting',
            scheduleKey: $scheduleKey,
            correlationId: 'corr-active',
            status: 'running',
            acceptedAt: $now,
            dueAt: $now->addSeconds(15),
            expiresAt: $now->addSeconds(120),
            details: [],
        );

        $active = $this->store->findActiveByScheduleKey($scheduleKey, $now);
        $this->assertNotNull($active);
        $this->assertSame('task-active', $active->task_id);
    }

    public function test_mark_terminal_touch_polled_and_cleanup(): void
    {
        $zone = Zone::factory()->create();
        $acceptedAt = CarbonImmutable::parse('2026-02-20 13:00:00', 'UTC');

        $this->store->upsertTaskSnapshot(
            taskId: 'task-cleanup',
            zoneId: $zone->id,
            taskType: 'ventilation',
            scheduleKey: 'zone:'.$zone->id.'|type:ventilation|interval=60',
            correlationId: 'corr-cleanup',
            status: 'accepted',
            acceptedAt: $acceptedAt,
            dueAt: $acceptedAt->addSeconds(15),
            expiresAt: $acceptedAt->addSeconds(120),
            details: ['step' => 'accepted'],
        );

        $polledAt = $acceptedAt->addSeconds(20);
        $this->store->touchPolledAt('task-cleanup', $polledAt, 'running');

        $terminalAt = $acceptedAt->addSeconds(30);
        $this->store->markTerminal(
            taskId: 'task-cleanup',
            status: 'timeout',
            terminalAt: $terminalAt,
            detailsPatch: ['terminal_source' => 'unit-test'],
            lastPolledAt: $polledAt,
        );

        $updated = $this->store->findByTaskId('task-cleanup');
        $this->assertNotNull($updated);
        $this->assertSame('timeout', $updated->status);
        $this->assertNotNull($updated->terminal_at);
        $this->assertSame('unit-test', $updated->details['terminal_source'] ?? null);

        DB::table('laravel_scheduler_active_tasks')
            ->where('task_id', 'task-cleanup')
            ->update(['terminal_at' => $acceptedAt->subDays(80)->toDateTimeString()]);

        $deleted = $this->store->cleanupTerminalOlderThan($acceptedAt->subDays(60), 100);
        $this->assertSame(1, $deleted);
        $this->assertDatabaseMissing('laravel_scheduler_active_tasks', [
            'task_id' => 'task-cleanup',
        ]);
    }
}
