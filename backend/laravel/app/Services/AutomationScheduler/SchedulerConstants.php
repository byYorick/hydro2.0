<?php

namespace App\Services\AutomationScheduler;

final class SchedulerConstants
{
    public const ACTIVE_CYCLE_STATUSES = [
        'PLANNED',
        'RUNNING',
        'PAUSED',
    ];

    public const TASK_NAME_PREFIX = 'laravel_scheduler_task';

    public const CYCLE_LOG_TASK_NAME = 'laravel_scheduler_cycle';

    public const METRICS_LOG_TASK_NAME = 'laravel_scheduler_metrics';

    public const TERMINAL_STATUSES = [
        'completed',
        'done',
        'failed',
        'rejected',
        'expired',
        'timeout',
        'error',
        'cancelled',
        'not_found',
    ];

    public const SUPPORTED_TASK_TYPES = [
        'irrigation',
        'lighting',
        'ventilation',
        'solution_change',
        'mist',
        'diagnostics',
    ];

    public const CATCHUP_POLICIES = [
        'skip',
        'replay_limited',
        'replay_all',
    ];

    public const METRIC_DISPATCHES_TOTAL = 'laravel_scheduler_dispatches_total';

    public const METRIC_CYCLE_DURATION_SECONDS = 'laravel_scheduler_cycle_duration_seconds';

    public const METRIC_ACTIVE_TASKS_COUNT = 'laravel_scheduler_active_tasks_count';

    public const ACTIVE_ZONE_STATUSES_LOWER = [
        'online',
        'warning',
        'running',
        'paused',
    ];

    public static function normalizeTerminalStatus(?string $status): string
    {
        $normalized = strtolower(trim((string) $status));
        if ($normalized === 'done') {
            return 'completed';
        }
        if ($normalized === 'error') {
            return 'failed';
        }

        return $normalized;
    }
}
