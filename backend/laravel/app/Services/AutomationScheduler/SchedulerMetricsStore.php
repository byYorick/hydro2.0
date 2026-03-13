<?php

namespace App\Services\AutomationScheduler;

use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Schema;

class SchedulerMetricsStore
{
    public function recordDispatchTotals(array $dispatchMetrics): void
    {
        if ($dispatchMetrics === [] || ! Schema::hasTable('laravel_scheduler_dispatch_metric_totals')) {
            return;
        }

        $timestamp = SchedulerRuntimeHelper::nowUtc()->toDateTimeString();

        foreach ($dispatchMetrics as $key => $value) {
            [$zoneId, $taskType, $result] = array_pad(explode('|', (string) $key, 3), 3, '');
            $increment = max(0, (int) $value);
            if ($increment <= 0) {
                continue;
            }

            DB::statement(
                <<<'SQL'
                INSERT INTO laravel_scheduler_dispatch_metric_totals
                    (zone_id, task_type, result, total, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT (zone_id, task_type, result) DO UPDATE
                SET total = laravel_scheduler_dispatch_metric_totals.total + EXCLUDED.total,
                    updated_at = EXCLUDED.updated_at
                SQL,
                [
                    (int) $zoneId,
                    (string) $taskType,
                    (string) $result,
                    $increment,
                    $timestamp,
                    $timestamp,
                ],
            );
        }
    }

    public function observeCycleDuration(string $dispatchMode, float $durationSeconds): void
    {
        if (
            ! Schema::hasTable('laravel_scheduler_cycle_duration_aggregates')
            || ! Schema::hasTable('laravel_scheduler_cycle_duration_bucket_counts')
        ) {
            return;
        }

        $mode = trim($dispatchMode) !== '' ? trim($dispatchMode) : 'start_cycle';
        $duration = max(0.0, $durationSeconds);
        $timestamp = SchedulerRuntimeHelper::nowUtc()->toDateTimeString();

        DB::statement(
            <<<'SQL'
            INSERT INTO laravel_scheduler_cycle_duration_aggregates
                (dispatch_mode, sample_count, sample_sum, created_at, updated_at)
            VALUES (?, 1, ?, ?, ?)
            ON CONFLICT (dispatch_mode) DO UPDATE
            SET sample_count = laravel_scheduler_cycle_duration_aggregates.sample_count + 1,
                sample_sum = laravel_scheduler_cycle_duration_aggregates.sample_sum + EXCLUDED.sample_sum,
                updated_at = EXCLUDED.updated_at
            SQL,
            [$mode, $duration, $timestamp, $timestamp],
        );

        foreach (SchedulerConstants::CYCLE_DURATION_BUCKETS as $bucket) {
            if ($duration > $bucket) {
                continue;
            }

            DB::statement(
                <<<'SQL'
                INSERT INTO laravel_scheduler_cycle_duration_bucket_counts
                    (dispatch_mode, bucket_le, sample_count, created_at, updated_at)
                VALUES (?, ?, 1, ?, ?)
                ON CONFLICT (dispatch_mode, bucket_le) DO UPDATE
                SET sample_count = laravel_scheduler_cycle_duration_bucket_counts.sample_count + 1,
                    updated_at = EXCLUDED.updated_at
                SQL,
                [$mode, $this->formatMetricValue($bucket), $timestamp, $timestamp],
            );
        }
    }

    private function formatMetricValue(float $value): string
    {
        $formatted = rtrim(rtrim(number_format($value, 6, '.', ''), '0'), '.');

        return $formatted === '' ? '0' : $formatted;
    }
}
