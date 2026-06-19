<?php

namespace Tests\Unit\Services\AutomationScheduler;

use App\Services\AutomationScheduler\ScheduleItem;
use InvalidArgumentException;
use Tests\TestCase;

class ScheduleItemTest extends TestCase
{
    public function test_it_normalizes_time_and_builds_deterministic_schedule_key(): void
    {
        $item = new ScheduleItem(
            zoneId: 7,
            taskType: 'IRRIGATION',
            time: '6:15',
            intervalSec: 60,
        );

        $this->assertSame(7, $item->zoneId);
        $this->assertSame('irrigation', $item->taskType);
        $this->assertSame('06:15:00', $item->time);
        $this->assertSame(60, $item->intervalSec);
        $this->assertSame('zone:7|type:irrigation|time=06:15:00|start=None|end=None|interval=60', $item->scheduleKey);
    }

    public function test_with_payload_keeps_same_identity_fields(): void
    {
        $item = new ScheduleItem(zoneId: 3, taskType: 'lighting', startTime: '22:00:00', endTime: '02:00:00');
        $next = $item->withPayload(['catchup_policy' => 'replay_limited']);

        $this->assertSame($item->scheduleKey, $next->scheduleKey);
        $this->assertSame('22:00:00', $next->startTime);
        $this->assertSame('02:00:00', $next->endTime);
        $this->assertSame(['catchup_policy' => 'replay_limited'], $next->payload);
    }

    public function test_it_validates_invalid_inputs(): void
    {
        $this->expectException(InvalidArgumentException::class);

        new ScheduleItem(zoneId: 0, taskType: 'lighting');
    }

    public function test_schedule_key_appends_days_suffix_only_when_days_set(): void
    {
        $plain = new ScheduleItem(zoneId: 1, taskType: 'irrigation', time: '08:00:00');
        $withDays = new ScheduleItem(zoneId: 1, taskType: 'irrigation', time: '08:00:00', daysOfWeek: [1, 3]);

        $this->assertSame(
            'zone:1|type:irrigation|time=08:00:00|start=None|end=None|interval=None',
            $plain->scheduleKey,
        );
        $this->assertStringEndsWith('|days=1,3', $withDays->scheduleKey);
    }

    public function test_schedule_key_is_stable_for_manual_schedules(): void
    {
        $plain = new ScheduleItem(
            zoneId: 2,
            taskType: 'lighting',
            manualScheduleId: 9,
            time: '08:00:00',
            intervalSec: 3600,
            runAt: '2026-06-20T12:00:00Z',
        );

        $this->assertSame('zone:2|manual:9', $plain->scheduleKey);
    }
}
