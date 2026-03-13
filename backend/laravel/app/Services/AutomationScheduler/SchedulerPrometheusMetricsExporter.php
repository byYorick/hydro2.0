<?php

namespace App\Services\AutomationScheduler;

use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Schema;

class SchedulerPrometheusMetricsExporter
{
    public function __construct(
        private readonly ActiveTaskStore $activeTaskStore,
    ) {}

    public function render(): string
    {
        $lines = [
            ...$this->renderDispatchCounters(),
            '',
            ...$this->renderCycleDurationHistogram(),
            '',
            ...$this->renderActiveTasksGauge(),
            '',
        ];

        return implode("\n", $lines);
    }

    /**
     * @return list<string>
     */
    private function renderDispatchCounters(): array
    {
        $lines = [
            '# HELP '.SchedulerConstants::METRIC_DISPATCHES_TOTAL.' Total scheduler dispatch attempts grouped by zone, task type, and result.',
            '# TYPE '.SchedulerConstants::METRIC_DISPATCHES_TOTAL.' counter',
        ];

        if (! Schema::hasTable('laravel_scheduler_dispatch_metric_totals')) {
            return $lines;
        }

        $rows = DB::table('laravel_scheduler_dispatch_metric_totals')
            ->select(['zone_id', 'task_type', 'result', 'total'])
            ->orderBy('zone_id')
            ->orderBy('task_type')
            ->orderBy('result')
            ->get();

        foreach ($rows as $row) {
            $lines[] = $this->renderMetricLine(
                SchedulerConstants::METRIC_DISPATCHES_TOTAL,
                [
                    'zone_id' => (string) ($row->zone_id ?? ''),
                    'task_type' => (string) ($row->task_type ?? ''),
                    'result' => (string) ($row->result ?? ''),
                ],
                (float) ($row->total ?? 0),
            );
        }

        return $lines;
    }

    /**
     * @return list<string>
     */
    private function renderCycleDurationHistogram(): array
    {
        $metricName = SchedulerConstants::METRIC_CYCLE_DURATION_SECONDS;
        $lines = [
            '# HELP '.$metricName.' Scheduler cycle duration histogram grouped by dispatch mode.',
            '# TYPE '.$metricName.' histogram',
        ];

        if (
            ! Schema::hasTable('laravel_scheduler_cycle_duration_aggregates')
            || ! Schema::hasTable('laravel_scheduler_cycle_duration_bucket_counts')
        ) {
            return $lines;
        }

        $aggregateRows = DB::table('laravel_scheduler_cycle_duration_aggregates')
            ->select(['dispatch_mode', 'sample_count', 'sample_sum'])
            ->orderBy('dispatch_mode')
            ->get();
        $bucketRows = DB::table('laravel_scheduler_cycle_duration_bucket_counts')
            ->select(['dispatch_mode', 'bucket_le', 'sample_count'])
            ->orderBy('dispatch_mode')
            ->orderBy('bucket_le')
            ->get();

        /** @var array<string, array<string, int>> $bucketMap */
        $bucketMap = [];
        foreach ($bucketRows as $row) {
            $dispatchMode = (string) ($row->dispatch_mode ?? 'start_cycle');
            $bucketKey = (string) ($row->bucket_le ?? '');
            $bucketMap[$dispatchMode][$bucketKey] = (int) ($row->sample_count ?? 0);
        }

        foreach ($aggregateRows as $row) {
            $dispatchMode = (string) ($row->dispatch_mode ?? 'start_cycle');
            $histogramBuckets = $this->emptyBuckets();
            foreach ($bucketMap[$dispatchMode] ?? [] as $bucketKey => $sampleCount) {
                $histogramBuckets[$bucketKey] = $sampleCount;
            }

            foreach (SchedulerConstants::CYCLE_DURATION_BUCKETS as $bucket) {
                $bucketKey = $this->formatMetricValue($bucket);
                $lines[] = $this->renderMetricLine(
                    $metricName.'_bucket',
                    [
                        'dispatch_mode' => $dispatchMode,
                        'le' => $bucketKey,
                    ],
                    $histogramBuckets[$bucketKey] ?? 0,
                );
            }

            $lines[] = $this->renderMetricLine(
                $metricName.'_bucket',
                [
                    'dispatch_mode' => $dispatchMode,
                    'le' => '+Inf',
                ],
                (float) ($row->sample_count ?? 0),
            );
            $lines[] = $this->renderMetricLine(
                $metricName.'_sum',
                ['dispatch_mode' => $dispatchMode],
                (float) ($row->sample_sum ?? 0),
            );
            $lines[] = $this->renderMetricLine(
                $metricName.'_count',
                ['dispatch_mode' => $dispatchMode],
                (float) ($row->sample_count ?? 0),
            );
        }

        return $lines;
    }

    /**
     * @return list<string>
     */
    private function renderActiveTasksGauge(): array
    {
        $metricName = SchedulerConstants::METRIC_ACTIVE_TASKS_COUNT;
        $activeTasks = 0;
        if (Schema::hasTable('laravel_scheduler_active_tasks')) {
            $activeTasks = $this->activeTaskStore->countActiveTasks(SchedulerRuntimeHelper::nowUtc());
        }

        return [
            '# HELP '.$metricName.' Current number of non-terminal scheduler tasks.',
            '# TYPE '.$metricName.' gauge',
            $this->renderMetricLine($metricName, [], $activeTasks),
        ];
    }

    /**
     * @return array<string, int>
     */
    private function emptyBuckets(): array
    {
        $buckets = [];
        foreach (SchedulerConstants::CYCLE_DURATION_BUCKETS as $bucket) {
            $buckets[$this->formatMetricValue($bucket)] = 0;
        }

        return $buckets;
    }

    /**
     * @param  array<string, string>  $labels
     */
    private function renderMetricLine(string $metricName, array $labels, int|float $value): string
    {
        if ($labels !== []) {
            ksort($labels);
            $pairs = [];
            foreach ($labels as $name => $labelValue) {
                if ($labelValue === '') {
                    continue;
                }
                $pairs[] = sprintf('%s="%s"', $name, $this->escapeLabelValue($labelValue));
            }
            if ($pairs !== []) {
                return sprintf('%s{%s} %s', $metricName, implode(',', $pairs), $this->formatMetricValue($value));
            }
        }

        return sprintf('%s %s', $metricName, $this->formatMetricValue($value));
    }

    private function escapeLabelValue(string $value): string
    {
        return str_replace(
            ["\\", "\n", '"'],
            ["\\\\", "\\n", '\\"'],
            $value,
        );
    }

    private function formatMetricValue(int|float $value): string
    {
        $floatValue = (float) $value;
        if ((float) ((int) $floatValue) === $floatValue) {
            return (string) ((int) $floatValue);
        }

        $formatted = rtrim(rtrim(sprintf('%.12F', $floatValue), '0'), '.');

        return $formatted === '-0' ? '0' : $formatted;
    }
}
