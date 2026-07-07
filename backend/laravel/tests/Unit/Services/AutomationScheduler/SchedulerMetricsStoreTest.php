<?php

namespace Tests\Unit\Services\AutomationScheduler;

use App\Models\Zone;
use App\Services\AutomationScheduler\SchedulerConstants;
use App\Services\AutomationScheduler\SchedulerMetricsStore;
use Carbon\CarbonImmutable;
use Illuminate\Support\Carbon;
use Illuminate\Support\Facades\DB;
use Tests\RefreshDatabase;
use Tests\TestCase;

class SchedulerMetricsStoreTest extends TestCase
{
    use RefreshDatabase;

    public function test_plan_summary_for_zone_sums_metric_logs_in_lookback(): void
    {
        Carbon::setTestNow(CarbonImmutable::parse('2026-07-07 12:00:00', 'UTC'));
        $zone = Zone::factory()->create();
        $since = CarbonImmutable::parse('2026-07-07 00:00:00', 'UTC');

        $this->insertMetricLog(
            $zone->id,
            SchedulerConstants::METRIC_MISSED_WINDOWS_TOTAL,
            ['zone_id' => $zone->id, 'task_type' => 'irrigation'],
            3,
            CarbonImmutable::parse('2026-07-07 10:00:00', 'UTC'),
        );
        $this->insertMetricLog(
            $zone->id,
            SchedulerConstants::METRIC_DISPATCHES_TOTAL,
            ['zone_id' => $zone->id, 'task_type' => 'irrigation', 'result' => 'backpressure'],
            2,
            CarbonImmutable::parse('2026-07-07 11:00:00', 'UTC'),
        );
        $this->insertMetricLog(
            $zone->id,
            SchedulerConstants::METRIC_DISPATCHES_TOTAL,
            ['zone_id' => $zone->id, 'task_type' => 'irrigation', 'result' => 'backpressure'],
            1,
            CarbonImmutable::parse('2026-07-05 12:00:00', 'UTC'),
        );

        /** @var SchedulerMetricsStore $store */
        $store = $this->app->make(SchedulerMetricsStore::class);
        $summary = $store->planSummaryForZone($zone->id, $since);

        $this->assertSame(3, $summary['missed_total']);
        $this->assertSame(2, $summary['suppressed_total']);

        Carbon::setTestNow();
    }

    /**
     * @param  array<string, int|string>  $labels
     */
    private function insertMetricLog(
        int $zoneId,
        string $metric,
        array $labels,
        int $value,
        CarbonImmutable $createdAt,
    ): void {
        DB::table('scheduler_logs')->insert([
            'task_name' => SchedulerConstants::METRICS_LOG_TASK_NAME,
            'status' => 'metric',
            'details' => json_encode([
                'metric' => $metric,
                'labels' => $labels,
                'value' => $value,
            ], JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES),
            'created_at' => $createdAt->toDateTimeString(),
        ]);
    }
}
