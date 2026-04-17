<?php

namespace Tests\Feature;

use App\Models\AutomationEffectiveBundle;
use App\Models\Greenhouse;
use App\Models\GrowCycle;
use App\Models\Zone;
use App\Services\AutomationConfigDocumentService;
use App\Services\AutomationConfigRegistry;
use Tests\RefreshDatabase;
use Tests\TestCase;

/**
 * Feature tests for automation:backfill-effective-bundles Artisan command.
 *
 * Covers Phase 4.1 of AE_LEGACY_CLEANUP_PLAN.md:
 * verifies that the backfill command correctly detects and repairs
 * automation_effective_bundles records with missing required sections.
 */
class BackfillEffectiveBundlesCommandTest extends TestCase
{
    use RefreshDatabase;

    private function makeZoneWithBundle(array $bundleConfigOverrides = []): Zone
    {
        $docs = app(AutomationConfigDocumentService::class);
        $docs->ensureSystemDefaults();

        $greenhouse = Greenhouse::factory()->create();
        $zone = Zone::factory()->create(['greenhouse_id' => $greenhouse->id]);
        $docs->ensureZoneDefaults($zone->id);

        // Allow overriding the compiled bundle config to simulate partial/old bundles.
        if ($bundleConfigOverrides !== []) {
            AutomationEffectiveBundle::query()->updateOrCreate(
                ['scope_type' => AutomationConfigRegistry::SCOPE_ZONE, 'scope_id' => $zone->id],
                ['config' => $bundleConfigOverrides, 'status' => 'valid', 'bundle_revision' => 'test-legacy',
                    'schema_revision' => '1', 'compiled_at' => now(), 'inputs_checksum' => 'test']
            );
        }

        return $zone;
    }

    public function test_dry_run_does_not_write_changes(): void
    {
        $zone = $this->makeZoneWithBundle(['zone' => []]);  // Missing required sections.

        $bundleBefore = AutomationEffectiveBundle::query()
            ->where('scope_type', AutomationConfigRegistry::SCOPE_ZONE)
            ->where('scope_id', $zone->id)
            ->value('bundle_revision');

        $this->artisan('automation:backfill-effective-bundles --scope=zone --dry-run')
            ->assertExitCode(0);

        $bundleAfter = AutomationEffectiveBundle::query()
            ->where('scope_type', AutomationConfigRegistry::SCOPE_ZONE)
            ->where('scope_id', $zone->id)
            ->value('bundle_revision');

        $this->assertSame($bundleBefore, $bundleAfter, 'Dry run must not modify bundle_revision');
    }

    public function test_validate_only_does_not_recompile(): void
    {
        $zone = $this->makeZoneWithBundle(['zone' => []]);

        $bundleBefore = AutomationEffectiveBundle::query()
            ->where('scope_type', AutomationConfigRegistry::SCOPE_ZONE)
            ->where('scope_id', $zone->id)
            ->value('bundle_revision');

        $this->artisan('automation:backfill-effective-bundles --scope=zone --validate-only')
            ->assertExitCode(0);

        $bundleAfter = AutomationEffectiveBundle::query()
            ->where('scope_type', AutomationConfigRegistry::SCOPE_ZONE)
            ->where('scope_id', $zone->id)
            ->value('bundle_revision');

        $this->assertSame($bundleBefore, $bundleAfter, 'Validate-only must not modify bundle');
    }

    public function test_zone_bundle_backfill_adds_missing_sections(): void
    {
        // Simulate an old bundle with only partial config (missing zone.pid, zone.process_calibration).
        $zone = $this->makeZoneWithBundle([
            'schema_version' => 1,
            'zone' => [
                'logic_profile' => ['active_mode' => 'two_tank'],
                'correction' => ['resolved_config' => []],
                // Missing: zone.pid, zone.process_calibration
            ],
        ]);

        $this->artisan('automation:backfill-effective-bundles --scope=zone')
            ->assertExitCode(0);

        $bundle = AutomationEffectiveBundle::query()
            ->where('scope_type', AutomationConfigRegistry::SCOPE_ZONE)
            ->where('scope_id', $zone->id)
            ->firstOrFail();

        $config = $bundle->config;
        $this->assertIsArray(data_get($config, 'zone.pid'), 'zone.pid must be present after backfill');
        $this->assertIsArray(data_get($config, 'zone.process_calibration'), 'zone.process_calibration must be present after backfill');
    }

    public function test_zone_with_complete_bundle_is_not_recompiled(): void
    {
        $zone = $this->makeZoneWithBundle();  // Full compilation via ensureZoneDefaults.

        $bundleBefore = AutomationEffectiveBundle::query()
            ->where('scope_type', AutomationConfigRegistry::SCOPE_ZONE)
            ->where('scope_id', $zone->id)
            ->value('bundle_revision');

        $this->artisan('automation:backfill-effective-bundles --scope=zone')
            ->assertExitCode(0);

        $bundleAfter = AutomationEffectiveBundle::query()
            ->where('scope_type', AutomationConfigRegistry::SCOPE_ZONE)
            ->where('scope_id', $zone->id)
            ->value('bundle_revision');

        // A complete bundle should not be recompiled (bundle_revision stays the same).
        $this->assertSame($bundleBefore, $bundleAfter, 'Complete bundle must not be recompiled');
    }

    public function test_dry_run_and_validate_only_cannot_combine(): void
    {
        $this->artisan('automation:backfill-effective-bundles --dry-run --validate-only')
            ->assertExitCode(1);
    }

    public function test_invalid_scope_returns_failure(): void
    {
        $this->artisan('automation:backfill-effective-bundles --scope=unknown')
            ->assertExitCode(1);
    }

    public function test_scope_system_does_nothing_and_succeeds(): void
    {
        // --scope=system is valid but currently has no processable records —
        // the command should exit cleanly without touching zones or grow_cycles.
        $zone = $this->makeZoneWithBundle(['zone' => []]);  // Bundle with missing sections.

        $bundleBefore = AutomationEffectiveBundle::query()
            ->where('scope_type', AutomationConfigRegistry::SCOPE_ZONE)
            ->where('scope_id', $zone->id)
            ->value('bundle_revision');

        $this->artisan('automation:backfill-effective-bundles --scope=system')
            ->assertExitCode(0);

        $bundleAfter = AutomationEffectiveBundle::query()
            ->where('scope_type', AutomationConfigRegistry::SCOPE_ZONE)
            ->where('scope_id', $zone->id)
            ->value('bundle_revision');

        $this->assertSame($bundleBefore, $bundleAfter, '--scope=system must not touch zone bundles');
    }
}
