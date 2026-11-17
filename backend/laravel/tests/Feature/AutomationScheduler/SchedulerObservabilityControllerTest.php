<?php

namespace Tests\Feature\AutomationScheduler;

use App\Models\User;
use App\Models\Zone;
use App\Services\AutomationScheduler\SchedulerMetricsStore;
use Carbon\CarbonImmutable;
use Illuminate\Support\Facades\Config;
use Illuminate\Support\Facades\DB;
use Tests\RefreshDatabase;
use Tests\TestCase;

class SchedulerObservabilityControllerTest extends TestCase
{
    use RefreshDatabase;

    public function test_ui_requires_authentication(): void
    {
        $this->getJson('/api/system/scheduler/observability')->assertUnauthorized();
    }

    public function test_authenticated_reader_works_without_scrape_token_and_keeps_metrics_protected(): void
    {
        Config::set('services.automation_engine.scheduler_metrics_token', 'fixture-scrape-secret');
        $this->get('/api/system/scheduler/metrics')->assertUnauthorized();
        $this->actingAs(User::factory()->create(['role' => 'viewer']))
            ->getJson('/api/system/scheduler/observability')->assertOk()
            ->assertJsonPath('data.scope', 'global')
            ->assertDontSee('fixture-scrape-secret');
    }

    public function test_no_recorded_cycle_is_not_reported_as_a_live_dispatcher_or_zero_latency(): void
    {
        Config::set('services.automation_engine.laravel_scheduler_enabled', true);
        DB::table('laravel_scheduler_cycle_duration_aggregates')->delete();
        $this->actingAs(User::factory()->create())->getJson('/api/system/scheduler/observability')
            ->assertOk()->assertJsonPath('data.cycle_observation', 'not_observed')
            ->assertJsonPath('data.last_cycle_at', null)->assertJsonPath('data.cycle_overrun_sec', null)
            ->assertJsonPath('data.oldest_pending_age_sec', null);
    }

    public function test_cycle_freshness_and_pending_age_are_evidence_with_utc_dates(): void
    {
        $this->travelTo(CarbonImmutable::parse('2026-11-17T12:00:00Z'));
        Config::set('services.automation_engine.laravel_scheduler_enabled', true);
        Config::set('services.automation_engine.scheduler_dispatch_interval_sec', 60);
        app(SchedulerMetricsStore::class)->observeCycleDuration('start_cycle', 0.2);
        $zone = Zone::factory()->create();
        DB::table('zone_automation_intents')->insert([
            'zone_id' => $zone->id, 'intent_type' => 'IRRIGATE_ONCE',
            'idempotency_key' => 'dispatcher-evidence', 'status' => 'pending',
            'payload' => '{}', 'created_at' => now()->subSeconds(30), 'updated_at' => now(),
        ]);
        $this->actingAs(User::factory()->create())->getJson('/api/system/scheduler/observability')
            ->assertOk()->assertJsonPath('data.cycle_observation', 'recent')
            ->assertJsonPath('data.pending_intents', 1)->assertJsonPath('data.oldest_pending_age_sec', 30)
            ->assertJsonPath('data.last_cycle_at', '2026-11-17T12:00:00+00:00');
        $this->travel(121)->seconds();
        $this->getJson('/api/system/scheduler/observability')->assertJsonPath('data.cycle_observation', 'delayed');
    }

    public function test_dispatch_credentials_presence_is_visible_without_exposing_the_secret(): void
    {
        Config::set('services.automation_engine.scheduler_api_token', 'fixture-private-dispatch-token');
        $this->actingAs(User::factory()->create())->getJson('/api/system/scheduler/observability')
            ->assertOk()->assertJsonPath('data.dispatch_token_configured', true)
            ->assertDontSee('fixture-private-dispatch-token');
    }

    public function test_disabled_dispatcher_is_explicit(): void
    {
        Config::set('services.automation_engine.laravel_scheduler_enabled', false);
        $this->actingAs(User::factory()->create())->getJson('/api/system/scheduler/observability')
            ->assertOk()->assertJsonPath('data.enabled', false)->assertJsonPath('data.cycle_observation', 'disabled');
    }
}
