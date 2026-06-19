<?php

namespace Tests\Unit\Services\AutomationScheduler;

use App\Models\ZoneManualSchedule;
use App\Services\AutomationScheduler\ManualScheduleItemBuilder;
use App\Services\AutomationScheduler\ScheduleItem;
use Tests\TestCase;

class ManualScheduleItemBuilderTest extends TestCase
{
    public function test_builds_manual_time_schedule_with_unique_key(): void
    {
        $row = new ZoneManualSchedule([
            'zone_id' => 7,
            'task_type' => 'irrigation',
            'schedule_kind' => 'time',
            'time_at' => '08:15:00',
            'payload' => ['duration_sec' => 60],
            'enabled' => true,
        ]);
        $row->id = 42;

        $builder = new ManualScheduleItemBuilder;
        $item = $builder->toScheduleItem($row);

        $this->assertNotNull($item);
        $this->assertSame(42, $item->manualScheduleId);
        $this->assertSame('08:15:00', $item->time);
        $this->assertStringContainsString('manual:42', $item->scheduleKey);
        $this->assertSame('manual', $item->payload['origin'] ?? null);
        $this->assertSame(60, $item->payload['duration_sec'] ?? null);
    }

    public function test_builds_once_schedule_with_run_at(): void
    {
        $row = new ZoneManualSchedule([
            'zone_id' => 3,
            'task_type' => 'lighting',
            'schedule_kind' => 'once',
            'run_at' => '2026-06-20 12:00:00',
            'payload' => [],
            'enabled' => true,
        ]);
        $row->id = 9;

        $item = (new ManualScheduleItemBuilder)->toScheduleItem($row);

        $this->assertInstanceOf(ScheduleItem::class, $item);
        $this->assertSame('2026-06-20T12:00:00Z', $item->runAt);
    }

    public function test_skips_once_schedule_after_dispatch(): void
    {
        $row = new ZoneManualSchedule([
            'zone_id' => 3,
            'task_type' => 'lighting',
            'schedule_kind' => 'once',
            'run_at' => '2026-06-20 12:00:00',
            'payload' => [],
            'enabled' => false,
        ]);
        $row->id = 9;
        $row->setAttribute('last_dispatched_at', '2026-06-20 12:00:05');

        $this->assertNull((new ManualScheduleItemBuilder)->toScheduleItem($row));
    }

    public function test_builds_interval_with_days_of_week(): void
    {
        $row = new ZoneManualSchedule([
            'zone_id' => 1,
            'task_type' => 'irrigation',
            'schedule_kind' => 'interval',
            'interval_sec' => 3600,
            'days_of_week' => [1, 3, 5],
            'payload' => [],
            'enabled' => true,
        ]);
        $row->id = 5;

        $item = (new ManualScheduleItemBuilder)->toScheduleItem($row);

        $this->assertNotNull($item);
        $this->assertSame(3600, $item->intervalSec);
        $this->assertSame([1, 3, 5], $item->daysOfWeek);
    }

    public function test_skips_interval_shorter_than_sixty_seconds(): void
    {
        $row = new ZoneManualSchedule([
            'zone_id' => 1,
            'task_type' => 'irrigation',
            'schedule_kind' => 'interval',
            'interval_sec' => 30,
            'payload' => [],
            'enabled' => true,
        ]);
        $row->id = 5;

        $this->assertNull((new ManualScheduleItemBuilder)->toScheduleItem($row));
    }
}
