<?php

namespace App\Services\AutomationScheduler;

use App\Services\AutomationRuntimeConfigService;
use Carbon\CarbonImmutable;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Schema;

/** Read-only global aggregates for operators; does not expose scrape credentials or per-zone data. */
class SchedulerDispatchReadModel
{
    public function __construct(
        private readonly SchedulerMetricsStore $metrics,
        private readonly AutomationRuntimeConfigService $config,
    ) {}

    public function snapshot(): array
    {
        $now = SchedulerRuntimeHelper::nowUtc();
        $cfg = $this->config->schedulerConfig();
        $interval = (int) $cfg['dispatch_interval_sec'];
        $enabled = $this->config->schedulerEnabled();
        $pending = null;
        $oldestAge = null;
        if (Schema::hasTable('zone_automation_intents')) {
            $row = DB::table('zone_automation_intents')->where('status', 'pending')
                ->selectRaw('count(*) as total, min(created_at) as oldest')->first();
            $pending = (int) $row->total;
            $oldestAge = $row->oldest === null ? null : $this->age($row->oldest, $now);
        }

        $last = null;
        if (Schema::hasTable('laravel_scheduler_cycle_duration_aggregates')) {
            $last = DB::table('laravel_scheduler_cycle_duration_aggregates')
                ->where('dispatch_mode', 'start_cycle')->where('sample_count', '>', 0)->value('updated_at');
        }
        $lastAge = $last === null ? null : $this->age($last, $now);
        $p99 = $this->metrics->estimateCycleDurationP99('start_cycle');

        return [
            'scope' => 'global',
            'generated_at' => $now->toIso8601String(),
            'enabled' => $enabled,
            'dispatch_token_configured' => trim((string) ($cfg['token'] ?? '')) !== '',
            'dispatch_interval_sec' => $interval,
            'last_cycle_at' => $last === null ? null : CarbonImmutable::parse($last, 'UTC')->toIso8601String(),
            'last_cycle_age_sec' => $lastAge,
            // Recent observation is evidence of a recorded cycle, never proof of a healthy worker.
            'cycle_observation' => ! $enabled ? 'disabled' : ($lastAge === null ? 'not_observed' : ($lastAge > 2 * $interval ? 'delayed' : 'recent')),
            'pending_intents' => $pending,
            'oldest_pending_age_sec' => $oldestAge,
            'cycle_duration_p99_sec' => $p99,
            'cycle_overrun_sec' => $p99 === null ? null : max(0.0, $p99 - $interval),
        ];
    }

    private function age(mixed $at, CarbonImmutable $now): float
    {
        return max(0.0, (float) ($now->getTimestamp() - CarbonImmutable::parse($at, 'UTC')->getTimestamp()));
    }
}
