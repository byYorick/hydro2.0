<?php

namespace Tests\Unit\Services;

use App\Models\Alert;
use App\Models\Zone;
use App\Services\AutomationConfigRegistry;
use App\Services\ZoneCorrectionConfigService;
use Tests\RefreshDatabase;
use Tests\TestCase;

class ZoneCorrectionConfigServiceTest extends TestCase
{
    use RefreshDatabase;

    private ZoneCorrectionConfigService $service;

    protected function setUp(): void
    {
        parent::setUp();

        $this->service = app(ZoneCorrectionConfigService::class);
    }

    public function test_ensure_default_for_zone_bootstraps_valid_defaults_when_config_is_missing(): void
    {
        $zone = Zone::factory()->create();

        $this->service->ensureDefaultForZone($zone->id);

        $config = $this->service->getOrCreateForZone($zone->id);

        $this->assertSame(1, (int) $config->version);
        $this->assertSame('irrig', data_get($config->base_config, 'runtime.required_node_type'));
        $this->assertSame('cross_coupled_pi_d', data_get($config->base_config, 'controllers.ph.mode'));
        $this->assertSame(100, data_get($config->base_config, 'dosing.solution_volume_l'));
        $this->assertSame([], $config->phase_overrides);
        $this->assertSame('irrig', data_get($config->resolved_config, 'base.runtime.required_node_type'));
        $this->assertSame('cross_coupled_pi_d', data_get($config->resolved_config, 'base.controllers.ph.mode'));

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

    public function test_ensure_default_for_zone_repairs_empty_bootstrap_config_and_resolves_stale_alert(): void
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

        $this->assertSame(1, (int) $config->version);
        $this->assertSame('irrig', data_get($config->base_config, 'runtime.required_node_type'));
        $this->assertSame('cross_coupled_pi_d', data_get($config->base_config, 'controllers.ph.mode'));
        $this->assertSame([], $config->phase_overrides);
        $this->assertSame('irrig', data_get($config->resolved_config, 'base.runtime.required_node_type'));

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
}
