<?php

namespace Tests\Feature;

use App\Models\User;
use App\Models\Zone;
use App\Services\ZoneAutomationStateService;
use Illuminate\Support\Facades\Cache;
use Illuminate\Support\Facades\Http;
use Inertia\Testing\AssertableInertia;
use Tests\RefreshDatabase;
use Tests\TestCase;

class ZoneShowAutomationStateTest extends TestCase
{
    use RefreshDatabase;

    private function automationEngineUrl(): string
    {
        return rtrim((string) config('services.automation_engine.api_url', 'http://automation-engine:9405'), '/');
    }

    public function test_zone_show_includes_cached_automation_state_bootstrap(): void
    {
        Cache::flush();

        $user = User::factory()->create(['role' => 'admin']);
        $zone = Zone::factory()->create();
        $apiUrl = $this->automationEngineUrl();

        Http::fake([
            "{$apiUrl}/zones/{$zone->id}/state" => Http::response([
                'zone_id' => $zone->id,
                'state' => 'IRRIGATING',
                'state_label' => 'Полив',
                'state_details' => [
                    'elapsed_sec' => 30,
                    'progress_percent' => 70,
                    'failed' => false,
                ],
                'system_config' => [
                    'tanks_count' => 2,
                    'system_type' => 'drip',
                ],
                'current_levels' => [],
                'active_processes' => [],
                'timeline' => [],
            ], 200),
        ]);

        $cachedPayload = [
            'zone_id' => $zone->id,
            'state' => 'TANK_FILLING',
            'state_label' => 'Наполнение баков',
            'state_details' => [
                'elapsed_sec' => 12,
                'progress_percent' => 10,
                'failed' => false,
            ],
            'system_config' => [
                'tanks_count' => 2,
                'system_type' => 'drip',
            ],
            'current_levels' => [],
            'active_processes' => [],
            'timeline' => [],
        ];

        app(ZoneAutomationStateService::class)->cacheState($zone->id, $cachedPayload);

        $this->actingAs($user)
            ->get("/zones/{$zone->id}")
            ->assertOk()
            ->assertInertia(function (AssertableInertia $page) use ($zone): void {
                $page->component('Zones/Show')
                    ->has('automationStateBootstrap')
                    ->where('automationStateBootstrap.zone_id', $zone->id)
                    ->where('automationStateBootstrap.state', 'TANK_FILLING')
                    ->where('automationStateBootstrap.state_meta.source', 'cache')
                    ->where('automationStateBootstrap.state_meta.is_stale', true)
                    ->loadDeferredProps(function (AssertableInertia $deferred) use ($zone): void {
                        $deferred->where('automationState.zone_id', $zone->id)
                            ->where('automationState.state', 'IRRIGATING')
                            ->where('automationState.state_meta.source', 'live')
                            ->where('automationState.state_meta.is_stale', false);
                    });
            });
    }

    public function test_zone_show_deferred_automation_state_returns_null_when_upstream_unavailable_without_cache(): void
    {
        Cache::flush();

        $user = User::factory()->create(['role' => 'admin']);
        $zone = Zone::factory()->create();
        $apiUrl = $this->automationEngineUrl();

        Http::fake([
            "{$apiUrl}/zones/{$zone->id}/state" => Http::response(['message' => 'upstream down'], 503),
        ]);

        $this->actingAs($user)
            ->get("/zones/{$zone->id}")
            ->assertOk()
            ->assertInertia(function (AssertableInertia $page): void {
                $page->component('Zones/Show')
                    ->where('automationStateBootstrap', null)
                    ->loadDeferredProps(function (AssertableInertia $deferred): void {
                        $deferred->where('automationState', null);
                    });
            });
    }
}
