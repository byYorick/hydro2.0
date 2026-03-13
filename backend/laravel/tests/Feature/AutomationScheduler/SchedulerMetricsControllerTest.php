<?php

namespace Tests\Feature\AutomationScheduler;

use App\Models\LaravelSchedulerActiveTask;
use App\Models\SchedulerLog;
use App\Models\Zone;
use App\Services\AutomationScheduler\SchedulerConstants;
use App\Services\AutomationScheduler\SchedulerMetricsStore;
use Carbon\CarbonImmutable;
use Illuminate\Support\Facades\DB;
use Tests\RefreshDatabase;
use Tests\TestCase;

class SchedulerMetricsControllerTest extends TestCase
{
    use RefreshDatabase;

    public function test_metrics_endpoint_renders_prometheus_scheduler_metrics(): void
    {
        $zone = Zone::factory()->create([
            'status' => 'online',
            'automation_runtime' => 'ae3',
        ]);

        /** @var SchedulerMetricsStore $metricsStore */
        $metricsStore = $this->app->make(SchedulerMetricsStore::class);
        $metricsStore->recordDispatchTotals([
            sprintf('%d|%s|%s', $zone->id, 'irrigation', 'accepted') => 2,
        ]);
        $metricsStore->recordDispatchTotals([
            sprintf('%d|%s|%s', $zone->id, 'irrigation', 'accepted') => 1,
        ]);
        $metricsStore->observeCycleDuration('start_cycle', 0.3);
        $metricsStore->observeCycleDuration('start_cycle', 1.2);

        $this->createMetricLog(
            SchedulerConstants::METRIC_DISPATCHES_TOTAL,
            ['zone_id' => $zone->id, 'task_type' => 'irrigation', 'result' => 'accepted'],
            999,
        );
        DB::table('scheduler_logs')->delete();

        LaravelSchedulerActiveTask::query()->create([
            'task_id' => 'task-active-1',
            'zone_id' => $zone->id,
            'task_type' => 'irrigation',
            'schedule_key' => 'schedule-key-1',
            'correlation_id' => 'corr-1',
            'status' => 'accepted',
            'accepted_at' => CarbonImmutable::parse('2026-03-12 12:00:00', 'UTC'),
            'due_at' => CarbonImmutable::parse('2026-03-12 12:01:00', 'UTC'),
            'expires_at' => null,
            'details' => [],
        ]);
        LaravelSchedulerActiveTask::query()->create([
            'task_id' => 'task-terminal-1',
            'zone_id' => $zone->id,
            'task_type' => 'irrigation',
            'schedule_key' => 'schedule-key-2',
            'correlation_id' => 'corr-2',
            'status' => 'completed',
            'accepted_at' => CarbonImmutable::parse('2026-03-12 11:50:00', 'UTC'),
            'due_at' => CarbonImmutable::parse('2026-03-12 11:51:00', 'UTC'),
            'expires_at' => CarbonImmutable::parse('2026-03-12 11:55:00', 'UTC'),
            'terminal_at' => CarbonImmutable::parse('2026-03-12 11:52:00', 'UTC'),
            'details' => [],
        ]);

        $response = $this->get('/api/system/scheduler/metrics');

        $response->assertOk();
        $response->assertHeader('content-type', 'text/plain; version=0.0.4; charset=utf-8');

        $body = $response->getContent();
        $this->assertIsString($body);
        $this->assertStringContainsString('# TYPE laravel_scheduler_dispatches_total counter', $body);
        $this->assertStringContainsString(
            'laravel_scheduler_dispatches_total{result="accepted",task_type="irrigation",zone_id="'.$zone->id.'"} 3',
            $body,
        );
        $this->assertStringContainsString('# TYPE laravel_scheduler_cycle_duration_seconds histogram', $body);
        $this->assertStringContainsString(
            'laravel_scheduler_cycle_duration_seconds_bucket{dispatch_mode="start_cycle",le="0.5"} 1',
            $body,
        );
        $this->assertStringContainsString(
            'laravel_scheduler_cycle_duration_seconds_bucket{dispatch_mode="start_cycle",le="2.5"} 2',
            $body,
        );
        $this->assertStringContainsString(
            'laravel_scheduler_cycle_duration_seconds_count{dispatch_mode="start_cycle"} 2',
            $body,
        );
        $this->assertStringContainsString(
            'laravel_scheduler_cycle_duration_seconds_sum{dispatch_mode="start_cycle"} 1.5',
            $body,
        );
        $this->assertStringContainsString('laravel_scheduler_active_tasks_count 1', $body);
        $this->assertStringNotContainsString('999', $body);
    }

    /**
     * @param  array<string, int|string>  $labels
     */
    private function createMetricLog(string $metric, array $labels, int|float $value): void
    {
        SchedulerLog::query()->create([
            'task_name' => SchedulerConstants::METRICS_LOG_TASK_NAME,
            'status' => 'metric',
            'details' => [
                'metric' => $metric,
                'labels' => $labels,
                'value' => $value,
            ],
        ]);
    }
}
