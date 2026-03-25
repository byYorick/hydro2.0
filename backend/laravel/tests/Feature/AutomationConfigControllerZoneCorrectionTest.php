<?php

namespace Tests\Feature;

use App\Models\User;
use App\Models\Zone;
use App\Services\AutomationConfigDocumentService;
use App\Services\AutomationConfigRegistry;
use App\Services\ZoneCorrectionConfigCatalog;
use Tests\RefreshDatabase;
use Tests\TestCase;

class AutomationConfigControllerZoneCorrectionTest extends TestCase
{
    use RefreshDatabase;

    public function test_zone_correction_show_returns_current_revision_in_resolved_config_meta(): void
    {
        $zone = Zone::factory()->create();
        $documents = app(AutomationConfigDocumentService::class);

        $documents->ensureZoneDefaults($zone->id);
        $current = $documents->getPayload(
            AutomationConfigRegistry::NAMESPACE_ZONE_CORRECTION,
            AutomationConfigRegistry::SCOPE_ZONE,
            $zone->id
        );
        $nextBaseConfig = is_array($current['base_config'] ?? null)
            ? $current['base_config']
            : ZoneCorrectionConfigCatalog::defaults();
        data_set($nextBaseConfig, 'timing.stabilization_sec', 75);

        $documents->upsertDocument(
            AutomationConfigRegistry::NAMESPACE_ZONE_CORRECTION,
            AutomationConfigRegistry::SCOPE_ZONE,
            $zone->id,
            [
                'base_config' => $nextBaseConfig,
                'phase_overrides' => [],
            ]
        );

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
