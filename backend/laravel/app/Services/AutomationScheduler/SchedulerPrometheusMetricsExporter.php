<?php

namespace App\Services\AutomationScheduler;

use Carbon\CarbonImmutable;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Schema;
use App\Services\AutomationRuntimeConfigService;

class SchedulerPrometheusMetricsExporter
{
    public function __construct(
        private readonly ActiveTaskStore $activeTaskStore,
        private readonly SchedulerMetricsStore $schedulerMetricsStore,
        private readonly AutomationRuntimeConfigService $runtimeConfig,
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
            ...$this->renderIntentLagGauges(),
            '',
            ...$this->renderZoneConfigAutoRevertsCounter(),
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
     * Phase 5 / R12 mitigation: публикует per-zone счётчик auto-revert событий
     * TTL-крона. Вычисляется из audit trail `zone_config_changes` —
     * `RevertExpiredLiveModesCommand` пишет туда строку с
     * `diff_json->auto_reverted = true`, так что отдельная counter-таблица не
     * нужна: audit — само монотонное хранилище событий.
     *
     * Используется Alertmanager rule: `rate(...[24h]) == 0 AND sum(ae3_zone_config_mode == 1) > 0`
     * — длинная live-сессия без auto-revert'ов сигнализирует о залипшем кроне.
     *
     * @return list<string>
     */
    private function renderZoneConfigAutoRevertsCounter(): array
    {
        $metricName = SchedulerConstants::METRIC_ZONE_CONFIG_AUTO_REVERTS_TOTAL;
        $lines = [
            '# HELP '.$metricName.' Total zones auto-reverted from live to locked by TTL cron, per zone.',
            '# TYPE '.$metricName.' counter',
        ];

        if (! Schema::hasTable('zone_config_changes')) {
            return $lines;
        }

        $rows = DB::table('zone_config_changes')
            ->selectRaw('zone_id, COUNT(*) AS total')
            ->where('namespace', 'zone.config_mode')
            ->whereRaw("diff_json ->> 'auto_reverted' = 'true'")
            ->groupBy('zone_id')
            ->orderBy('zone_id')
            ->get();

        foreach ($rows as $row) {
            $lines[] = $this->renderMetricLine(
                $metricName,
                ['zone_id' => (string) ($row->zone_id ?? '')],
                (float) ($row->total ?? 0),
            );
        }

        return $lines;
    }

    /**
     * @return list<string>
     */
    private function renderIntentLagGauges(): array
    {
        $pendingMetric = SchedulerConstants::METRIC_PENDING_INTENTS_COUNT;
        $oldestAgeMetric = SchedulerConstants::METRIC_OLDEST_PENDING_INTENT_AGE_SECONDS;
        $overrunMetric = SchedulerConstants::METRIC_DISPATCH_CYCLE_OVERRUN_SECONDS;

        $pendingCount = 0;
        $oldestPendingAgeSeconds = 0.0;
        if (Schema::hasTable('zone_automation_intents')) {
            $pendingCount = (int) DB::table('zone_automation_intents')
                ->where('status', 'pending')
                ->count();
            $oldestPendingAt = DB::table('zone_automation_intents')
                ->where('status', 'pending')
                ->min('created_at');
            if ($oldestPendingAt !== null) {
                try {
                    if ($oldestPendingAt instanceof \DateTimeInterface) {
                        $oldestTs = CarbonImmutable::instance($oldestPendingAt)->utc()->setMicroseconds(0);
                    } else {
                        $oldestTs = CarbonImmutable::parse((string) $oldestPendingAt, 'UTC')->setMicroseconds(0);
                    }
                    $oldestPendingAgeSeconds = max(
                        0.0,
                        (float) (SchedulerRuntimeHelper::nowUtc()->getTimestamp() - $oldestTs->getTimestamp()),
                    );
                } catch (\Throwable) {
                    $oldestPendingAgeSeconds = 0.0;
                }
            }
        }

        $dispatchIntervalSec = max(1, (int) ($this->runtimeConfig->schedulerConfig()['dispatch_interval_sec'] ?? 60));
        $p99CycleDurationSec = $this->schedulerMetricsStore->estimateCycleDurationP99('start_cycle') ?? 0.0;
        $dispatchCycleOverrun = max(0.0, $p99CycleDurationSec - $dispatchIntervalSec);

        return [
            '# HELP '.$pendingMetric.' Current number of scheduler intents in pending status.',
            '# TYPE '.$pendingMetric.' gauge',
            $this->renderMetricLine($pendingMetric, [], $pendingCount),
            '# HELP '.$oldestAgeMetric.' Age in seconds of the oldest pending scheduler intent.',
            '# TYPE '.$oldestAgeMetric.' gauge',
            $this->renderMetricLine($oldestAgeMetric, [], $oldestPendingAgeSeconds),
            '# HELP '.$overrunMetric.' Positive difference between p99 scheduler cycle duration and dispatch interval.',
            '# TYPE '.$overrunMetric.' gauge',
            $this->renderMetricLine($overrunMetric, [], $dispatchCycleOverrun),
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
