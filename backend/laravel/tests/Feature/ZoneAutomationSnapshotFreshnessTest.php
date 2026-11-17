<?php

namespace Tests\Feature;

use App\Models\Zone;
use App\Services\ZoneAutomationStateService;
use Illuminate\Support\Facades\Cache;
use Tests\RefreshDatabase;
use Tests\TestCase;

class ZoneAutomationSnapshotFreshnessTest extends TestCase
{
    use RefreshDatabase;

    public function test_serving_cached_state_does_not_renew_its_capture_time(): void
    {
        $this->travelTo(now()->startOfSecond());
        $zone = Zone::factory()->create();
        $service = app(ZoneAutomationStateService::class);
        $service->cacheState($zone->id, ['zone_id' => $zone->id, 'state' => 'IDLE']);
        $capturedAt = now()->toIso8601String();
        $this->travel(120)->seconds();
        $snapshot = $service->resolveCachedBootstrap($zone);
        $this->assertSame($capturedAt, $snapshot['state_meta']['observed_at']);
        $this->assertSame(now()->toIso8601String(), $snapshot['state_meta']['served_at']);
        $this->assertTrue($snapshot['state_meta']['is_stale']);
        $service->cacheState($zone->id, ['zone_id' => $zone->id, 'state' => 'READY']);
        $this->assertSame(now()->toIso8601String(), $service->resolveCachedBootstrap($zone)['state_meta']['observed_at']);
    }

    public function test_legacy_cache_has_unknown_capture_time(): void
    {
        $zone = Zone::factory()->create();
        $service = app(ZoneAutomationStateService::class);
        Cache::put($service->stateCacheKey($zone->id), ['zone_id' => $zone->id, 'state' => 'IDLE'], 300);
        $this->assertNull($service->resolveCachedBootstrap($zone)['state_meta']['observed_at']);
    }
}
