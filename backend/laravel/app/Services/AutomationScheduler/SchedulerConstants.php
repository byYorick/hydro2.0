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

    public const METRIC_PENDING_INTENTS_COUNT = 'laravel_scheduler_pending_intents_count';

    public const METRIC_OLDEST_PENDING_INTENT_AGE_SECONDS = 'laravel_scheduler_oldest_pending_intent_age_seconds';

    public const METRIC_DISPATCH_CYCLE_OVERRUN_SECONDS = 'laravel_scheduler_dispatch_cycle_overrun_seconds';

    public const METRIC_ZONE_CONFIG_AUTO_REVERTS_TOTAL = 'ae3_zone_config_auto_reverts_total';

    /** @var list<float> */
    public const CYCLE_DURATION_BUCKETS = [0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0, 120.0, 300.0, 600.0];

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
