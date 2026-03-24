<?php

namespace Tests\Feature;

use App\Models\User;
use App\Models\Zone;
use App\Services\ZoneCorrectionConfigurationService;
use Tests\RefreshDatabase;
use Tests\TestCase;

class AutomationConfigControllerZoneCorrectionTest extends TestCase
{
    use RefreshDatabase;

    public function test_zone_correction_show_returns_current_revision_in_resolved_config_meta(): void
    {
        $zone = Zone::factory()->create();
        $service = app(ZoneCorrectionConfigurationService::class);

        $service->ensureDefaultForZone($zone->id);

        $current = $service->getOrCreateForZone($zone->id);
        $nextBaseConfig = $current->baseConfig;
        data_set($nextBaseConfig, 'timing.stabilization_sec', 75);

        $service->upsert($zone->id, [
            'base_config' => $nextBaseConfig,
            'phase_overrides' => [],
        ]);

        $viewer = User::factory()->create(['role' => 'viewer']);

        $this->actingAs($viewer)
            ->getJson("/api/automation-configs/zone/{$zone->id}/zone.correction")
            ->assertOk()
            ->assertJsonPath('status', 'ok')
            ->assertJsonPath('data.version', 2)
            ->assertJsonPath('data.resolved_config.meta.version', 2)
            ->assertJsonPath('data.resolved_config.meta.phase_overrides', []);
    }
}
