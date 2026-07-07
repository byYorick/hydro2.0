<?php

namespace App\Services\AutomationScheduler;

use Carbon\CarbonImmutable;
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

    public function estimateCycleDurationP99(string $dispatchMode = 'start_cycle'): ?float
    {
        if (
            ! Schema::hasTable('laravel_scheduler_cycle_duration_aggregates')
            || ! Schema::hasTable('laravel_scheduler_cycle_duration_bucket_counts')
        ) {
            return null;
        }

        $mode = trim($dispatchMode) !== '' ? trim($dispatchMode) : 'start_cycle';
        $aggregate = DB::table('laravel_scheduler_cycle_duration_aggregates')
            ->where('dispatch_mode', $mode)
            ->first(['sample_count']);
        $sampleCount = max(0, (int) ($aggregate->sample_count ?? 0));
        if ($sampleCount <= 0) {
            return null;
        }

        $rank = (int) ceil($sampleCount * 0.99);
        $rank = max(1, $rank);
        $rows = DB::table('laravel_scheduler_cycle_duration_bucket_counts')
            ->where('dispatch_mode', $mode)
            ->orderByRaw('bucket_le::double precision')
            ->get(['bucket_le', 'sample_count']);

        foreach ($rows as $row) {
            $bucketCount = max(0, (int) ($row->sample_count ?? 0));
            if ($bucketCount >= $rank) {
                $bucket = (float) ($row->bucket_le ?? 0.0);

                return max(0.0, $bucket);
            }
        }

        return null;
    }

    private function formatMetricValue(float $value): string
    {
        $formatted = rtrim(rtrim(number_format($value, 6, '.', ''), '0'), '.');

        return $formatted === '' ? '0' : $formatted;
    }

    public function recordMissedWindowsTotal(int $zoneId, string $taskType, int $increment): void
    {
        if ($increment <= 0 || ! Schema::hasTable('laravel_scheduler_missed_windows_totals')) {
            return;
        }

        $timestamp = SchedulerRuntimeHelper::nowUtc()->toDateTimeString();
        DB::statement(
            <<<'SQL'
            INSERT INTO laravel_scheduler_missed_windows_totals
                (zone_id, task_type, total, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT (zone_id, task_type) DO UPDATE
            SET total = laravel_scheduler_missed_windows_totals.total + EXCLUDED.total,
                updated_at = EXCLUDED.updated_at
            SQL,
            [$zoneId, $taskType, $increment, $timestamp, $timestamp],
        );
    }

    public function recordLockSkippedTotal(int $increment = 1): void
    {
        if ($increment <= 0 || ! Schema::hasTable('laravel_scheduler_lock_skipped_totals')) {
            return;
        }

        $timestamp = SchedulerRuntimeHelper::nowUtc()->toDateTimeString();
        $existing = DB::table('laravel_scheduler_lock_skipped_totals')->orderBy('id')->first();
        if ($existing === null) {
            DB::table('laravel_scheduler_lock_skipped_totals')->insert([
                'total' => $increment,
                'created_at' => $timestamp,
                'updated_at' => $timestamp,
            ]);

            return;
        }

        DB::table('laravel_scheduler_lock_skipped_totals')
            ->where('id', $existing->id)
            ->update([
                'total' => (int) ($existing->total ?? 0) + $increment,
                'updated_at' => $timestamp,
            ]);
    }

    public function sumMetricLogInLookback(
        int $zoneId,
        string $metric,
        CarbonImmutable $since,
        ?string $result = null,
    ): int {
        if (! Schema::hasTable('scheduler_logs')) {
            return 0;
        }

        $query = DB::table('scheduler_logs')
            ->where('task_name', SchedulerConstants::METRICS_LOG_TASK_NAME)
            ->where('status', 'metric')
            ->where('created_at', '>=', $since->toDateTimeString())
            ->whereRaw("details->>'metric' = ?", [$metric])
            ->whereRaw("(details->'labels'->>'zone_id')::bigint = ?", [$zoneId]);

        if ($result !== null) {
            $query->whereRaw("details->'labels'->>'result' = ?", [$result]);
        }

        $rows = $query->get(['details']);
        $sum = 0;
        foreach ($rows as $row) {
            $details = is_string($row->details ?? null)
                ? json_decode($row->details, true)
                : (array) ($row->details ?? []);
            if (! is_array($details)) {
                continue;
            }
            $sum += max(0, (int) ($details['value'] ?? 0));
        }

        return $sum;
    }

    /**
     * @return array{missed_total: int, suppressed_total: int}
     */
    public function planSummaryForZone(int $zoneId, CarbonImmutable $since): array
    {
        $missedTotal = $this->sumMetricLogInLookback(
            $zoneId,
            SchedulerConstants::METRIC_MISSED_WINDOWS_TOTAL,
            $since,
        );

        if ($missedTotal === 0 && Schema::hasTable('laravel_scheduler_missed_windows_totals')) {
            $missedTotal = (int) DB::table('laravel_scheduler_missed_windows_totals')
                ->where('zone_id', $zoneId)
                ->where('updated_at', '>=', $since->toDateTimeString())
                ->sum('total');
        }

        $suppressedTotal = $this->sumMetricLogInLookback(
            $zoneId,
            SchedulerConstants::METRIC_DISPATCHES_TOTAL,
            $since,
            'backpressure',
        );

        return [
            'missed_total' => $missedTotal,
            'suppressed_total' => $suppressedTotal,
        ];
    }
}
