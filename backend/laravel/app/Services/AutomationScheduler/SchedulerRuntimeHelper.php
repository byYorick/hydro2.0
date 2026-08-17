<?php

namespace App\Services\AutomationScheduler;

use Carbon\CarbonImmutable;

final class SchedulerRuntimeHelper
{
    public static function toIso(CarbonImmutable $value): string
    {
        return $value->format('Y-m-d\TH:i:s\Z');
    }

    public static function nowUtc(): CarbonImmutable
    {
        return CarbonImmutable::now('UTC')->setMicroseconds(0);
    }

    public static function activeTaskCacheKey(string $scheduleKey): string
    {
        return 'laravel_scheduler_active:'.sha1($scheduleKey);
    }

    public static function scheduleTaskLogName(int $zoneId, string $taskType): string
    {
        return sprintf('%s_%s_zone_%d', SchedulerConstants::TASK_NAME_PREFIX, $taskType, $zoneId);
    }

    public static function intervalTaskLogName(int $zoneId, string $taskType, ?int $manualScheduleId = null): string
    {
        if ($manualScheduleId !== null && $manualScheduleId > 0) {
            return sprintf(
                '%s_%s_manual_%d_zone_%d',
                SchedulerConstants::TASK_NAME_PREFIX,
                strtolower(trim($taskType)),
                $manualScheduleId,
                $zoneId,
            );
        }

        return self::scheduleTaskLogName($zoneId, $taskType);
    }

    public static function intervalTaskLogNameForSchedule(ScheduleItem $schedule): string
    {
        return self::intervalTaskLogName(
            zoneId: $schedule->zoneId,
            taskType: $schedule->taskType,
            manualScheduleId: $schedule->manualScheduleId,
        );
    }

    public static function normalizeTimezone(?string $timezone): ?string
    {
        if ($timezone === null) {
            return null;
        }

        $normalized = trim($timezone);
        if ($normalized === '') {
            return null;
        }

        try {
            new \DateTimeZone($normalized);
        } catch (\Throwable) {
            return null;
        }

        return $normalized;
    }

    public static function intervalSlotAt(
        CarbonImmutable $now,
        int $intervalSec,
        ?CarbonImmutable $lastCompletedAt,
    ): CarbonImmutable {
        if ($intervalSec <= 0) {
            return $now;
        }

        if ($lastCompletedAt instanceof CarbonImmutable) {
            $due = $lastCompletedAt->addSeconds($intervalSec)->setMicroseconds(0);
            if ($due->lte($now)) {
                return $due;
            }
        }

        $bucketTs = intdiv($now->getTimestamp(), $intervalSec) * $intervalSec;

        return CarbonImmutable::createFromTimestamp($bucketTs, 'UTC')->setMicroseconds(0);
    }
}
