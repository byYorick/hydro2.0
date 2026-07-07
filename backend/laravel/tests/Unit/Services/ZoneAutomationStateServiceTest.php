<?php

namespace Tests\Unit\Services;

use App\Models\Zone;
use App\Services\ZoneAutomationStateService;
use Illuminate\Http\Client\Request as HttpRequest;
use Illuminate\Support\Facades\Cache;
use Illuminate\Support\Facades\Http;
use Tests\RefreshDatabase;
use Tests\TestCase;

class ZoneAutomationStateServiceTest extends TestCase
{
    use RefreshDatabase;

    private function automationEngineUrl(): string
    {
        return rtrim((string) config('services.automation_engine.api_url', 'http://automation-engine:9405'), '/');
    }

    public function test_resolve_cached_bootstrap_returns_decorated_cache_without_upstream_call(): void
    {
        Cache::flush();

        $zone = Zone::factory()->create(['control_mode' => 'semi']);
        $service = app(ZoneAutomationStateService::class);

        $service->cacheState($zone->id, [
            'zone_id' => $zone->id,
            'state' => 'READY',
            'state_label' => 'Раствор готов',
            'state_details' => ['failed' => false],
            'system_config' => ['tanks_count' => 2, 'system_type' => 'drip'],
            'current_levels' => [],
            'active_processes' => [],
            'timeline' => [],
        ]);

        Http::fake();

        $bootstrap = $service->resolveCachedBootstrap($zone->fresh());

        $this->assertNotNull($bootstrap);
        $this->assertSame('READY', $bootstrap['state']);
        $this->assertSame('semi', $bootstrap['control_mode']);
        $this->assertSame('cache', $bootstrap['state_meta']['source']);
        $this->assertTrue($bootstrap['state_meta']['is_stale']);

        Http::assertNothingSent();
    }

    public function test_resolve_for_api_caches_live_payload(): void
    {
        Cache::flush();

        config()->set('services.automation_engine.scheduler_api_token', 'test-scheduler-token');

        $zone = Zone::factory()->create();
        $apiUrl = $this->automationEngineUrl();
        $service = app(ZoneAutomationStateService::class);

        Http::fake([
            "{$apiUrl}/zones/{$zone->id}/state" => Http::response([
                'zone_id' => $zone->id,
                'state' => 'TANK_RECIRC',
                'state_label' => 'Рециркуляция',
                'state_details' => ['failed' => false],
                'system_config' => ['tanks_count' => 2, 'system_type' => 'drip'],
                'current_levels' => [],
                'active_processes' => [],
                'timeline' => [],
            ], 200),
        ]);

        $payload = $service->resolveForApi($zone);

        $this->assertSame('TANK_RECIRC', $payload['state']);
        $this->assertSame('live', $payload['state_meta']['source']);
        $this->assertFalse($payload['state_meta']['is_stale']);

        $cached = $service->getCachedState($zone->id);
        $this->assertIsArray($cached);
        $this->assertSame('TANK_RECIRC', $cached['state']);

        Http::assertSent(function (HttpRequest $request) use ($zone): bool {
            return $request->url() === "{$this->automationEngineUrl()}/zones/{$zone->id}/state"
                && $request->hasHeader('Authorization', 'Bearer test-scheduler-token')
                && $request->hasHeader('X-Trace-Id');
        });
    }

    public function test_resolve_returns_null_when_upstream_and_cache_unavailable(): void
    {
        Cache::flush();

        $zone = Zone::factory()->create();
        $apiUrl = $this->automationEngineUrl();
        $service = app(ZoneAutomationStateService::class);

        Http::fake([
            "{$apiUrl}/zones/{$zone->id}/state" => Http::response(['message' => 'down'], 503),
        ]);

        $this->assertNull($service->resolve($zone));
    }
}
