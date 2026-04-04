<?php

namespace Tests\Unit\Services\AutomationScheduler;

use App\Services\AutomationScheduler\LightingScheduleParser;
use App\Services\AutomationScheduler\ZoneScheduleItemBuilder;
use Carbon\CarbonImmutable;
use Tests\TestCase;

class ZoneScheduleItemBuilderTest extends TestCase
{
    public function test_irrigation_time_schedule_includes_duration_sec_payload_from_targets(): void
    {
        $builder = new ZoneScheduleItemBuilder(
            lightingScheduleParser: new LightingScheduleParser,
        );

        $targets = [
            'irrigation' => [
                'schedule' => ['08:00'],
                'duration_sec' => 90,
            ],
            'extensions' => [
                'subsystems' => [
                    'irrigation' => ['enabled' => true],
                ],
            ],
        ];

        $schedules = $builder->buildSchedulesForZone(5, $targets, CarbonImmutable::parse('2026-04-04 00:00:00', 'UTC'));

        $irrigation = array_values(array_filter($schedules, fn ($s) => $s->taskType === 'irrigation'));
        $this->assertNotEmpty($irrigation);
        $this->assertSame(['duration_sec' => 90], $irrigation[0]->payload);
    }

    public function test_irrigation_interval_schedule_includes_same_duration_payload(): void
    {
        $builder = new ZoneScheduleItemBuilder(
            lightingScheduleParser: new LightingScheduleParser,
        );

        $targets = [
            'irrigation' => [
                'interval_sec' => 3600,
                'duration_sec' => 45,
            ],
            'extensions' => [
                'subsystems' => [
                    'irrigation' => ['enabled' => true],
                ],
            ],
        ];

        $schedules = $builder->buildSchedulesForZone(2, $targets, CarbonImmutable::parse('2026-04-04 00:00:00', 'UTC'));

        $withInterval = array_values(array_filter($schedules, fn ($s) => $s->taskType === 'irrigation' && $s->intervalSec > 0));
        $this->assertNotEmpty($withInterval);
        $this->assertSame(['duration_sec' => 45], $withInterval[0]->payload);
    }
}
