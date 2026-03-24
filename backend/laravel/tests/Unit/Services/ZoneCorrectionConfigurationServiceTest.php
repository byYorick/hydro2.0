<?php

namespace Tests\Unit\Services;

use App\Models\Alert;
use App\Models\AutomationEffectiveBundle;
use App\Models\Zone;
use App\Services\AutomationConfigRegistry;
use App\Services\ZoneCorrectionConfigurationService;
use Tests\RefreshDatabase;
use Tests\TestCase;

class ZoneCorrectionConfigurationServiceTest extends TestCase
{
    use RefreshDatabase;

    private ZoneCorrectionConfigurationService $service;

    protected function setUp(): void
    {
        parent::setUp();
        $this->service = app(ZoneCorrectionConfigurationService::class);
    }

    public function test_ensure_default_for_zone_bootstraps_valid_defaults_when_config_is_missing(): void
    {
        $zone = Zone::factory()->create();

        $this->service->ensureDefaultForZone($zone->id);

        $config = $this->service->getOrCreateForZone($zone->id);

        $this->assertSame(1, $config->version);
        $this->assertSame('irrig', data_get($config->baseConfig, 'runtime.required_node_type'));
        $this->assertSame('cross_coupled_pi_d', data_get($config->baseConfig, 'controllers.ph.mode'));
        $this->assertSame(100, data_get($config->baseConfig, 'dosing.solution_volume_l'));
        $this->assertSame([], $config->phaseOverrides);
        $this->assertSame('irrig', data_get($config->resolvedConfig, 'base.runtime.required_node_type'));
        $this->assertSame('cross_coupled_pi_d', data_get($config->resolvedConfig, 'base.controllers.ph.mode'));

        $this->assertDatabaseHas('automation_config_documents', [
            'namespace' => AutomationConfigRegistry::NAMESPACE_ZONE_CORRECTION,
            'scope_type' => AutomationConfigRegistry::SCOPE_ZONE,
            'scope_id' => $zone->id,
        ]);
        $this->assertDatabaseHas('automation_config_versions', [
            'namespace' => AutomationConfigRegistry::NAMESPACE_ZONE_CORRECTION,
            'scope_type' => AutomationConfigRegistry::SCOPE_ZONE,
            'scope_id' => $zone->id,
            'source' => 'bootstrap',
        ]);
    }

    public function test_ensure_default_for_zone_resolves_stale_alert(): void
    {
        $zone = Zone::factory()->create();

        Alert::query()->create([
            'zone_id' => $zone->id,
            'source' => 'automation-engine',
            'code' => 'biz_zone_correction_config_missing',
            'type' => 'biz',
            'details' => [],
            'status' => 'ACTIVE',
            'category' => 'operations',
            'severity' => 'critical',
            'error_count' => 1,
            'first_seen_at' => now(),
            'last_seen_at' => now(),
            'created_at' => now(),
        ]);

        $this->service->getOrCreateForZone($zone->id);
        $this->service->ensureDefaultForZone($zone->id);

        $config = $this->service->getOrCreateForZone($zone->id);

        $this->assertSame(1, $config->version);
        $this->assertSame('irrig', data_get($config->baseConfig, 'runtime.required_node_type'));
        $this->assertSame('cross_coupled_pi_d', data_get($config->baseConfig, 'controllers.ph.mode'));
        $this->assertSame([], $config->phaseOverrides);
        $this->assertSame('irrig', data_get($config->resolvedConfig, 'base.runtime.required_node_type'));

        $this->assertDatabaseHas('automation_config_versions', [
            'namespace' => AutomationConfigRegistry::NAMESPACE_ZONE_CORRECTION,
            'scope_type' => AutomationConfigRegistry::SCOPE_ZONE,
            'scope_id' => $zone->id,
            'source' => 'bootstrap',
        ]);
        $this->assertDatabaseHas('alerts', [
            'zone_id' => $zone->id,
            'code' => 'biz_zone_correction_config_missing',
            'status' => 'RESOLVED',
        ]);
    }

    public function test_zone_correction_bundle_uses_current_document_revision_in_meta_version(): void
    {
        $zone = Zone::factory()->create();

        $this->service->ensureDefaultForZone($zone->id);

        /** @var AutomationEffectiveBundle $bundle */
        $bundle = AutomationEffectiveBundle::query()
            ->where('scope_type', AutomationConfigRegistry::SCOPE_ZONE)
            ->where('scope_id', $zone->id)
            ->firstOrFail();

        $this->assertSame(1, data_get($bundle->config, 'zone.correction.resolved_config.meta.version'));

        $current = $this->service->getOrCreateForZone($zone->id);
        $nextBaseConfig = $current->baseConfig;
        data_set($nextBaseConfig, 'timing.stabilization_sec', 75);

        $this->service->upsert($zone->id, [
            'base_config' => $nextBaseConfig,
            'phase_overrides' => [],
        ]);

        $bundle = AutomationEffectiveBundle::query()
            ->where('scope_type', AutomationConfigRegistry::SCOPE_ZONE)
            ->where('scope_id', $zone->id)
            ->firstOrFail();

        $this->assertSame(2, data_get($bundle->config, 'zone.correction.resolved_config.meta.version'));
    }
}
