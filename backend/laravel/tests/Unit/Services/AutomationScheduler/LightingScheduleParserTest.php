<?php

namespace Tests\Unit\Services\AutomationScheduler;

use App\Services\AutomationScheduler\LightingScheduleParser;
use Carbon\CarbonImmutable;
use Tests\TestCase;

class LightingScheduleParserTest extends TestCase
{
    public function test_parse_supports_photoperiod_plus_start_time(): void
    {
        $parser = new LightingScheduleParser;
        $items = $parser->parse(
            zoneId: 12,
            lightingConfig: [
                'start_time' => '08:00',
                'photoperiod_hours' => 10,
                'interval_sec' => 90,
            ],
            lightingScheduleSpec: null,
            nowUtc: CarbonImmutable::parse('2026-03-03 00:00:00', 'UTC'),
        );

        $this->assertCount(1, $items);
        $this->assertSame('08:00:00', $items[0]->startTime);
        $this->assertSame('18:00:00', $items[0]->endTime);
        $this->assertSame(90, $items[0]->intervalSec);
    }

    public function test_parse_supports_lighting_schedule_window_string(): void
    {
        $parser = new LightingScheduleParser;
        $items = $parser->parse(
            zoneId: 5,
            lightingConfig: [
                'interval_sec' => 120,
            ],
            lightingScheduleSpec: '06:30-19:45',
            nowUtc: CarbonImmutable::parse('2026-03-03 00:00:00', 'UTC'),
        );

        $this->assertCount(1, $items);
        $this->assertSame('06:30:00', $items[0]->startTime);
        $this->assertSame('19:45:00', $items[0]->endTime);
        $this->assertSame(120, $items[0]->intervalSec);
    }

    public function test_parse_falls_back_to_time_points_and_interval(): void
    {
        $parser = new LightingScheduleParser;
        $items = $parser->parse(
            zoneId: 9,
            lightingConfig: [
                'interval_sec' => 60,
            ],
            lightingScheduleSpec: ['times' => ['08:00', '20:00']],
            nowUtc: CarbonImmutable::parse('2026-03-03 00:00:00', 'UTC'),
        );

        $this->assertCount(3, $items);
        $this->assertSame('08:00:00', $items[0]->time);
        $this->assertSame('20:00:00', $items[1]->time);
        $this->assertSame(60, $items[2]->intervalSec);
        $this->assertNull($items[2]->time);
    }

    public function test_parse_keeps_midnight_crossing_window(): void
    {
        $parser = new LightingScheduleParser;
        $items = $parser->parse(
            zoneId: 4,
            lightingConfig: [
                'interval_sec' => 30,
            ],
            lightingScheduleSpec: '22:00-02:00',
            nowUtc: CarbonImmutable::parse('2026-03-03 00:00:00', 'UTC'),
        );

        $this->assertCount(1, $items);
        $this->assertSame('22:00:00', $items[0]->startTime);
        $this->assertSame('02:00:00', $items[0]->endTime);
    }
}
