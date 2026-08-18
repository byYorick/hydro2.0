<?php

namespace Tests\Unit\AutomationScheduler;

use App\Services\AutomationScheduler\SchedulerCycleFinalizer;
use Carbon\CarbonImmutable;
use PHPUnit\Framework\Attributes\DataProvider;
use Tests\TestCase;

class SchedulerCycleFinalizerMissedTicksTest extends TestCase
{
    #[DataProvider('missedTicksProvider')]
    public function test_count_missed_interval_ticks(
        string $lastCompletedAt,
        int $intervalSec,
        string $now,
        int $expected,
    ): void {
        $finalizer = $this->app->make(SchedulerCycleFinalizer::class);

        $missed = $finalizer->countMissedIntervalTicks(
            CarbonImmutable::parse($lastCompletedAt, 'UTC'),
            $intervalSec,
            CarbonImmutable::parse($now, 'UTC'),
        );

        $this->assertSame($expected, $missed);
    }

    /**
     * @return array<string, array{string, int, string, int}>
     */
    public static function missedTicksProvider(): array
    {
        return [
            'on-time due tick (exact)' => [
                '2026-07-14 11:00:00',
                3600,
                '2026-07-14 12:00:00',
                0,
            ],
            'late by one poll cycle is not a miss' => [
                '2026-07-14 11:00:00',
                3600,
                '2026-07-14 12:01:00',
                0,
            ],
            'one full interval skipped' => [
                '2026-07-14 11:00:00',
                3600,
                '2026-07-14 13:00:00',
                1,
            ],
            'two full intervals skipped' => [
                '2026-07-14 11:00:00',
                3600,
                '2026-07-14 14:05:00',
                2,
            ],
            'r6 scenario: 3.5 min late on 60s interval → 2 missed' => [
                '2026-07-07 11:56:30',
                60,
                '2026-07-07 12:00:00',
                2,
            ],
            'zero interval' => [
                '2026-07-14 11:00:00',
                0,
                '2026-07-14 12:00:00',
                0,
            ],
            'now before last' => [
                '2026-07-14 12:00:00',
                60,
                '2026-07-14 11:00:00',
                0,
            ],
        ];
    }

    public function test_window_boundary_at_uses_end_time_crossing_when_leaving_window(): void
    {
        $finalizer = $this->app->make(SchedulerCycleFinalizer::class);
        $boundary = $finalizer->windowBoundaryAt(
            last: CarbonImmutable::parse('2026-07-07 21:30:00', 'UTC'),
            now: CarbonImmutable::parse('2026-07-07 22:00:30', 'UTC'),
            startTime: '06:00:00',
            endTime: '22:00:00',
            enteringWindow: false,
        );

        $this->assertSame('2026-07-07 22:00:00', $boundary->format('Y-m-d H:i:s'));
    }

    public function test_window_boundary_at_uses_start_time_crossing_when_entering_window(): void
    {
        $finalizer = $this->app->make(SchedulerCycleFinalizer::class);
        $boundary = $finalizer->windowBoundaryAt(
            last: CarbonImmutable::parse('2026-07-07 05:50:00', 'UTC'),
            now: CarbonImmutable::parse('2026-07-07 06:00:20', 'UTC'),
            startTime: '06:00:00',
            endTime: '22:00:00',
            enteringWindow: true,
        );

        $this->assertSame('2026-07-07 06:00:00', $boundary->format('Y-m-d H:i:s'));
    }

    public function test_is_time_in_window_treats_end_boundary_as_off(): void
    {
        $finalizer = $this->app->make(SchedulerCycleFinalizer::class);

        $this->assertTrue($finalizer->isTimeInWindow('08:00:00', '08:00:00', '18:00:00'));
        $this->assertTrue($finalizer->isTimeInWindow('17:59:59', '08:00:00', '18:00:00'));
        $this->assertFalse($finalizer->isTimeInWindow('18:00:00', '08:00:00', '18:00:00'));
        $this->assertFalse($finalizer->isTimeInWindow('22:00:00', '08:00:00', '18:00:00'));
    }

    public function test_moscow_photoperiod_end_at_1500_utc_is_off_boundary(): void
    {
        $finalizer = $this->app->make(SchedulerCycleFinalizer::class);
        $last = CarbonImmutable::parse('2026-08-17 14:30:00', 'UTC');
        $now = CarbonImmutable::parse('2026-08-17 15:00:00', 'UTC');

        $this->assertTrue($finalizer->isTimeInWindow('15:00:00', '08:00:00', '18:00:00'));
        $this->assertTrue($finalizer->isUtcMomentInWindow($last, '08:00:00', '18:00:00', 'Europe/Moscow'));
        $this->assertFalse($finalizer->isUtcMomentInWindow($now, '08:00:00', '18:00:00', 'Europe/Moscow'));

        $boundary = $finalizer->windowBoundaryAt(
            last: $last,
            now: $now,
            startTime: '08:00:00',
            endTime: '18:00:00',
            enteringWindow: false,
            timezone: 'Europe/Moscow',
        );

        $this->assertSame('2026-08-17 15:00:00', $boundary->utc()->format('Y-m-d H:i:s'));
    }

    public function test_moscow_photoperiod_1900_utc_is_outside_window(): void
    {
        $finalizer = $this->app->make(SchedulerCycleFinalizer::class);
        $now = CarbonImmutable::parse('2026-08-17 19:00:00', 'UTC');

        $this->assertFalse($finalizer->isUtcMomentInWindow($now, '08:00:00', '18:00:00', 'Europe/Moscow'));
        $this->assertFalse($finalizer->isTimeInWindow($now->format('H:i:s'), '08:00:00', '18:00:00'));
    }
}
