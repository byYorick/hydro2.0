<?php

namespace Tests\Unit;

use App\Models\Zone;
use App\Services\ZoneAutomationIntentService;
use Illuminate\Support\Facades\DB;
use Tests\RefreshDatabase;
use Tests\TestCase;

class ZoneAutomationIntentServiceTest extends TestCase
{
    use RefreshDatabase;

    public function test_record_scheduler_dispatch_failure_increments_retry_before_terminal_fail(): void
    {
        $zone = Zone::factory()->create();
        $key = 'sch:z'.$zone->id.':diagnostics:unit-test';

        DB::table('zone_automation_intents')->insert([
            'zone_id' => $zone->id,
            'intent_type' => 'DIAGNOSTICS_TICK',
            'task_type' => 'cycle_start',
            'intent_source' => 'laravel_scheduler',
            'idempotency_key' => $key,
            'status' => 'pending',
            'not_before' => now(),
            'retry_count' => 0,
            'max_retries' => 3,
            'created_at' => now(),
            'updated_at' => now(),
        ]);

        /** @var ZoneAutomationIntentService $service */
        $service = $this->app->make(ZoneAutomationIntentService::class);

        $first = $service->recordSchedulerDispatchFailure(
            zoneId: $zone->id,
            idempotencyKey: $key,
            errorCode: 'scheduler_dispatch_http_error',
            errorMessage: 'HTTP 500',
        );
        $this->assertSame(['failed' => false, 'retry_count' => 1], $first);

        $second = $service->recordSchedulerDispatchFailure(
            zoneId: $zone->id,
            idempotencyKey: $key,
            errorCode: 'scheduler_dispatch_http_error',
            errorMessage: 'HTTP 500',
        );
        $this->assertSame(['failed' => false, 'retry_count' => 2], $second);

        $third = $service->recordSchedulerDispatchFailure(
            zoneId: $zone->id,
            idempotencyKey: $key,
            errorCode: 'scheduler_dispatch_http_error',
            errorMessage: 'HTTP 500',
        );
        $this->assertSame(['failed' => true, 'retry_count' => 3], $third);

        $this->assertDatabaseHas('zone_automation_intents', [
            'zone_id' => $zone->id,
            'idempotency_key' => $key,
            'status' => 'failed',
            'error_code' => 'scheduler_dispatch_http_error',
            'retry_count' => 3,
        ]);
    }

    public function test_sync_intent_failed_from_ae_task_marks_active_intent(): void
    {
        $zone = Zone::factory()->create();
        $key = 'reap-sync-intent-test';

        DB::table('zone_automation_intents')->insert([
            'zone_id' => $zone->id,
            'intent_type' => 'IRRIGATE_ONCE',
            'task_type' => 'irrigation_start',
            'intent_source' => 'laravel_scheduler',
            'idempotency_key' => $key,
            'status' => 'running',
            'not_before' => now(),
            'retry_count' => 0,
            'max_retries' => 3,
            'created_at' => now(),
            'updated_at' => now(),
        ]);

        /** @var ZoneAutomationIntentService $service */
        $service = $this->app->make(ZoneAutomationIntentService::class);
        $service->syncIntentFailedFromAeTask(
            zoneId: $zone->id,
            idempotencyKey: $key,
            errorCode: 'task_progress_stale',
            errorMessage: 'reaped by watchdog',
        );

        $this->assertDatabaseHas('zone_automation_intents', [
            'zone_id' => $zone->id,
            'idempotency_key' => $key,
            'status' => 'failed',
            'error_code' => 'task_progress_stale',
        ]);
    }

    public function test_sync_intent_failed_from_ae_task_requeues_transient_offline_error(): void
    {
        $zone = Zone::factory()->create();
        $key = 'reap-sync-transient-offline';

        DB::table('zone_automation_intents')->insert([
            'zone_id' => $zone->id,
            'intent_type' => 'IRRIGATE_ONCE',
            'task_type' => 'irrigation_start',
            'intent_source' => 'laravel_scheduler',
            'idempotency_key' => $key,
            'status' => 'running',
            'not_before' => now(),
            'retry_count' => 0,
            'max_retries' => 3,
            'created_at' => now(),
            'updated_at' => now(),
        ]);

        /** @var ZoneAutomationIntentService $service */
        $service = $this->app->make(ZoneAutomationIntentService::class);
        $service->syncIntentFailedFromAeTask(
            zoneId: $zone->id,
            idempotencyKey: $key,
            errorCode: 'ae3_required_node_offline',
            errorMessage: 'ph node offline',
        );

        $this->assertDatabaseHas('zone_automation_intents', [
            'zone_id' => $zone->id,
            'idempotency_key' => $key,
            'status' => 'pending',
            'error_code' => 'ae3_required_node_offline',
            'retry_count' => 1,
        ]);
    }
}
