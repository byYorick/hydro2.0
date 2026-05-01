<?php

namespace Tests\Feature\AutomationScheduler;

use App\Models\LaravelSchedulerActiveTask;
use App\Models\SchedulerLog;
use App\Models\Zone;
use App\Models\ZoneConfigChange;
use App\Services\AutomationScheduler\SchedulerConstants;
use App\Services\AutomationScheduler\SchedulerMetricsStore;
use Carbon\CarbonImmutable;
use Illuminate\Support\Carbon;
use Illuminate\Support\Facades\Config;
use Illuminate\Support\Facades\DB;
use Tests\RefreshDatabase;
use Tests\TestCase;

class SchedulerMetricsControllerTest extends TestCase
{
    use RefreshDatabase;

    public function test_metrics_endpoint_renders_prometheus_scheduler_metrics(): void
    {
        Carbon::setTestNow(CarbonImmutable::parse('2026-03-12 12:00:00', 'UTC'));
        Config::set('services.automation_engine.scheduler_dispatch_interval_sec', 1);

        $zone = Zone::factory()->create([
            'status' => 'online',
            'automation_runtime' => 'ae3',
        ]);

        /** @var SchedulerMetricsStore $metricsStore */
        $metricsStore = $this->app->make(SchedulerMetricsStore::class);
        $metricsStore->recordDispatchTotals([
            sprintf('%d|%s|%s', $zone->id, 'irrigation', 'success') => 2,
        ]);
        $metricsStore->recordDispatchTotals([
            sprintf('%d|%s|%s', $zone->id, 'irrigation', 'success') => 1,
        ]);
        $metricsStore->observeCycleDuration('start_cycle', 0.3);
        $metricsStore->observeCycleDuration('start_cycle', 1.2);

        $this->createMetricLog(
            SchedulerConstants::METRIC_DISPATCHES_TOTAL,
            ['zone_id' => $zone->id, 'task_type' => 'irrigation', 'result' => 'success'],
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
            'laravel_scheduler_dispatches_total{result="success",task_type="irrigation",zone_id="'.$zone->id.'"} 3',
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
        DB::table('zone_automation_intents')->insert([
            [
                'zone_id' => $zone->id,
                'intent_type' => 'IRRIGATE_ONCE',
                'payload' => json_encode(['source' => 'test']),
                'idempotency_key' => 'intent-pending-1',
                'status' => 'pending',
                'created_at' => CarbonImmutable::now('UTC')->subSeconds(120),
                'updated_at' => CarbonImmutable::now('UTC')->subSeconds(120),
            ],
            [
                'zone_id' => $zone->id,
                'intent_type' => 'IRRIGATE_ONCE',
                'payload' => json_encode(['source' => 'test']),
                'idempotency_key' => 'intent-pending-2',
                'status' => 'pending',
                'created_at' => CarbonImmutable::now('UTC')->subSeconds(30),
                'updated_at' => CarbonImmutable::now('UTC')->subSeconds(30),
            ],
        ]);

        $responseWithLag = $this->get('/api/system/scheduler/metrics');
        $responseWithLag->assertOk();
        $bodyWithLag = $responseWithLag->getContent();
        $this->assertIsString($bodyWithLag);
        $this->assertStringContainsString('laravel_scheduler_pending_intents_count 2', $bodyWithLag);
        $this->assertMatchesRegularExpression('/laravel_scheduler_oldest_pending_intent_age_seconds\s+1[0-9]{2}(\.0+)?/', $bodyWithLag);
        $this->assertStringContainsString('laravel_scheduler_dispatch_cycle_overrun_seconds 0', $bodyWithLag);
        $this->assertStringNotContainsString('999', $body);
        Carbon::setTestNow();
    }

    public function test_metrics_endpoint_renders_zone_config_auto_reverts_counter(): void
    {
        $zoneA = Zone::factory()->create();
        $zoneB = Zone::factory()->create();

        // Три auto-revert события для zoneA, одно для zoneB, одна ручная правка
        // (без auto_reverted=true) — последняя не должна попадать в counter.
        ZoneConfigChange::create([
            'zone_id' => $zoneA->id, 'revision' => 1,
            'namespace' => 'zone.config_mode',
            'diff_json' => ['from' => 'live', 'to' => 'locked', 'auto_reverted' => true],
            'user_id' => null, 'reason' => 'auto-revert',
            'created_at' => Carbon::now()->subHour(),
        ]);
        ZoneConfigChange::create([
            'zone_id' => $zoneA->id, 'revision' => 2,
            'namespace' => 'zone.config_mode',
            'diff_json' => ['from' => 'live', 'to' => 'locked', 'auto_reverted' => true],
            'user_id' => null, 'reason' => 'auto-revert',
            'created_at' => Carbon::now()->subMinutes(30),
        ]);
        ZoneConfigChange::create([
            'zone_id' => $zoneA->id, 'revision' => 3,
            'namespace' => 'zone.config_mode',
            'diff_json' => ['from' => 'live', 'to' => 'locked', 'auto_reverted' => true],
            'user_id' => null, 'reason' => 'auto-revert',
            'created_at' => Carbon::now(),
        ]);
        ZoneConfigChange::create([
            'zone_id' => $zoneB->id, 'revision' => 1,
            'namespace' => 'zone.config_mode',
            'diff_json' => ['from' => 'live', 'to' => 'locked', 'auto_reverted' => true],
            'user_id' => null, 'reason' => 'auto-revert',
            'created_at' => Carbon::now(),
        ]);
        // Manual revert от пользователя — НЕ должен инкрементировать counter.
        ZoneConfigChange::create([
            'zone_id' => $zoneA->id, 'revision' => 4,
            'namespace' => 'zone.config_mode',
            'diff_json' => ['from' => 'live', 'to' => 'locked'],
            'user_id' => null, 'reason' => 'manual',
            'created_at' => Carbon::now(),
        ]);

        $response = $this->get('/api/system/scheduler/metrics');
        $response->assertOk();

        $body = $response->getContent();
        $this->assertIsString($body);
        $this->assertStringContainsString('# TYPE ae3_zone_config_auto_reverts_total counter', $body);
        $this->assertStringContainsString(
            sprintf('ae3_zone_config_auto_reverts_total{zone_id="%d"} 3', $zoneA->id),
            $body,
        );
        $this->assertStringContainsString(
            sprintf('ae3_zone_config_auto_reverts_total{zone_id="%d"} 1', $zoneB->id),
            $body,
        );
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
