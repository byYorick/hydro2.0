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
}
