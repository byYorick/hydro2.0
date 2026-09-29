<?php

namespace Tests\Unit\Wave10;

use App\Models\Zone;
use App\Services\ZoneAutomationStateService;
use Illuminate\Support\Facades\Cache;
use Illuminate\Support\Facades\Http;
use Tests\TestCase;

class E254UnattendedInertiaStateTest extends TestCase
{
    public function test_e254_runtime_state_has_unattended_without_tank_stages(): void
    {
        Cache::flush();
        config()->set('services.automation_engine.scheduler_api_token', 'test-scheduler-token');

        $zone = Zone::factory()->create(['automation_runtime' => 'ae4']);
        $apiUrl = rtrim((string) config('services.automation_engine.api_url', 'http://automation-engine:9405'), '/');
        $service = app(ZoneAutomationStateService::class);

        Http::fake([
            "{$apiUrl}/zones/{$zone->id}/state" => Http::response([
                'zone_id' => $zone->id,
                'state' => 'IDLE',
                'state_label' => 'Ожидание',
                'state_details' => ['failed' => false],
                'unattended_ready' => true,
                'unattended_blockers' => [],
                'system_config' => [],
                'current_levels' => [],
                'active_processes' => [],
                'timeline' => [],
            ], 200),
        ]);

        $payload = $service->resolveForApi($zone);

        $this->assertArrayHasKey('unattended_ready', $payload);
        $this->assertTrue((bool) $payload['unattended_ready']);
        $this->assertIsArray($payload['unattended_blockers'] ?? null);
        $this->assertSame([], $payload['unattended_blockers']);

        $blob = json_encode($payload, JSON_UNESCAPED_UNICODE) ?: '';
        foreach (['tank_filling', 'tank_recirc', 'irrigating', 'TANK_FILLING', 'TANK_RECIRC'] as $stage) {
            $this->assertStringNotContainsString($stage, $blob);
        }
    }
}
