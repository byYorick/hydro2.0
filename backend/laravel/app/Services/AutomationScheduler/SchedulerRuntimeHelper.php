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
}
