<?php

namespace Tests\Feature;

use App\Models\AutomationConfigDocument;
use App\Models\AutomationEffectiveBundle;
use App\Models\Greenhouse;
use App\Models\GrowCycle;
use App\Models\Zone;
use App\Services\AutomationConfigCompiler;
use App\Services\AutomationConfigDocumentService;
use App\Services\AutomationConfigRegistry;
use Tests\RefreshDatabase;
use Tests\TestCase;

class CycleConfigOverridesTest extends TestCase
{
    use RefreshDatabase;

    private function setupZoneWithCycle(): array
    {
        $docs = app(AutomationConfigDocumentService::class);
        $docs->ensureSystemDefaults();

        $greenhouse = Greenhouse::factory()->create();
        $zone = Zone::factory()->create([
            'greenhouse_id' => $greenhouse->id,
        ]);
        $docs->ensureZoneDefaults($zone->id);

        $cycle = GrowCycle::factory()->running()->create([
            'greenhouse_id' => $greenhouse->id,
            'zone_id' => $zone->id,
        ]);
        $docs->ensureCycleDefaults($cycle->id);

        return [$zone, $cycle];
    }

    // --- Namespace registration ---

    public function test_config_overrides_namespace_registered(): void
    {
        $registry = app(AutomationConfigRegistry::class);
        $namespaces = $registry->namespaces();

        $this->assertContains('cycle.config_overrides', $namespaces);
    }

    public function test_config_overrides_namespace_has_correct_scope(): void
    {
        $registry = app(AutomationConfigRegistry::class);

        $this->assertEquals(
            AutomationConfigRegistry::SCOPE_GROW_CYCLE,
            $registry->scopeType(AutomationConfigRegistry::NAMESPACE_CYCLE_CONFIG_OVERRIDES),
        );
    }

    public function test_config_overrides_validation_rejects_list(): void
    {
        $registry = app(AutomationConfigRegistry::class);

        $this->expectException(\InvalidArgumentException::class);
        $registry->validate(AutomationConfigRegistry::NAMESPACE_CYCLE_CONFIG_OVERRIDES, ['item1', 'item2']);
    }

    public function test_config_overrides_validation_accepts_object(): void
    {
        $registry = app(AutomationConfigRegistry::class);

        // Empty object — OK
        $registry->validate(AutomationConfigRegistry::NAMESPACE_CYCLE_CONFIG_OVERRIDES, []);
        // Non-empty object — OK
        $registry->validate(AutomationConfigRegistry::NAMESPACE_CYCLE_CONFIG_OVERRIDES, ['logic_profile' => ['active_mode' => 'setup']]);

        $this->assertTrue(true);
    }

    // --- Bundle compilation without overrides (backward compatible) ---

    public function test_bundle_compiles_without_config_overrides(): void
    {
        [$zone, $cycle] = $this->setupZoneWithCycle();

        $compiler = app(AutomationConfigCompiler::class);
        $bundle = $compiler->compileGrowCycleBundle($cycle->id);

        $config = $bundle->config;
        $this->assertArrayHasKey('zone', $config);
        $this->assertArrayHasKey('cycle', $config);
        $this->assertEquals([], $config['cycle']['config_overrides'] ?? []);
    }

    // --- Bundle compilation with overrides ---

    public function test_bundle_merges_config_overrides_into_zone(): void
    {
        [$zone, $cycle] = $this->setupZoneWithCycle();
        $docs = app(AutomationConfigDocumentService::class);

        // Save config override that changes logic_profile active_mode
        $docs->upsertCycleDocuments($cycle->id, [
            AutomationConfigRegistry::NAMESPACE_CYCLE_CONFIG_OVERRIDES => [
                'logic_profile' => [
                    'active_mode' => 'overridden_mode',
                ],
            ],
        ]);

        $compiler = app(AutomationConfigCompiler::class);
        $bundle = $compiler->compileGrowCycleBundle($cycle->id);

        $config = $bundle->config;
        // Override should be applied to zone config
        $this->assertEquals('overridden_mode', data_get($config, 'zone.logic_profile.active_mode'));
        // Override payload preserved in cycle section
        $this->assertNotEmpty($config['cycle']['config_overrides']);
    }

    public function test_config_overrides_deep_merge_preserves_non_overridden_keys(): void
    {
        [$zone, $cycle] = $this->setupZoneWithCycle();
        $docs = app(AutomationConfigDocumentService::class);
        $compiler = app(AutomationConfigCompiler::class);

        // Compile zone bundle first to get baseline
        $compiler->compileZoneBundle($zone->id);
        $baselineBundle = $compiler->compileGrowCycleBundle($cycle->id);
        $baselineCorrection = data_get($baselineBundle->config, 'zone.correction');

        // Override only logic_profile.active_mode, correction should be preserved
        $docs->upsertCycleDocuments($cycle->id, [
            AutomationConfigRegistry::NAMESPACE_CYCLE_CONFIG_OVERRIDES => [
                'logic_profile' => [
                    'active_mode' => 'cycle_override_mode',
                ],
            ],
        ]);

        $overriddenBundle = $compiler->compileGrowCycleBundle($cycle->id);
        $overriddenConfig = $overriddenBundle->config;

        // Override applied
        $this->assertEquals('cycle_override_mode', data_get($overriddenConfig, 'zone.logic_profile.active_mode'));
        // Correction preserved (not touched by override)
        $this->assertEquals($baselineCorrection, data_get($overriddenConfig, 'zone.correction'));
    }

    public function test_empty_config_overrides_does_not_change_bundle(): void
    {
        [$zone, $cycle] = $this->setupZoneWithCycle();
        $docs = app(AutomationConfigDocumentService::class);
        $compiler = app(AutomationConfigCompiler::class);

        // Compile bundle without overrides
        $compiler->compileZoneBundle($zone->id);
        $bundleWithout = $compiler->compileGrowCycleBundle($cycle->id);
        $zoneConfigWithout = $bundleWithout->config['zone'] ?? [];

        // Save empty config overrides
        $docs->upsertCycleDocuments($cycle->id, [
            AutomationConfigRegistry::NAMESPACE_CYCLE_CONFIG_OVERRIDES => [],
        ]);

        // Recompile
        $bundleWith = $compiler->compileGrowCycleBundle($cycle->id);
        $zoneConfigWith = $bundleWith->config['zone'] ?? [];

        // Zone config should be identical
        $this->assertEquals($zoneConfigWithout, $zoneConfigWith);
    }

    // --- Deep merge unit tests ---

    public function test_deep_merge_replaces_scalar_values(): void
    {
        $compiler = app(AutomationConfigCompiler::class);
        $method = new \ReflectionMethod($compiler, 'deepMerge');

        $base = ['a' => 1, 'b' => 'hello', 'c' => true];
        $override = ['a' => 2, 'c' => false];

        $result = $method->invoke($compiler, $base, $override);

        $this->assertEquals(2, $result['a']);
        $this->assertEquals('hello', $result['b']);
        $this->assertFalse($result['c']);
    }

    public function test_deep_merge_recursively_merges_objects(): void
    {
        $compiler = app(AutomationConfigCompiler::class);
        $method = new \ReflectionMethod($compiler, 'deepMerge');

        $base = [
            'level1' => [
                'keep' => 'original',
                'change' => 'old',
                'nested' => ['deep_keep' => 1, 'deep_change' => 2],
            ],
        ];
        $override = [
            'level1' => [
                'change' => 'new',
                'nested' => ['deep_change' => 99],
            ],
        ];

        $result = $method->invoke($compiler, $base, $override);

        $this->assertEquals('original', $result['level1']['keep']);
        $this->assertEquals('new', $result['level1']['change']);
        $this->assertEquals(1, $result['level1']['nested']['deep_keep']);
        $this->assertEquals(99, $result['level1']['nested']['deep_change']);
    }

    public function test_deep_merge_replaces_indexed_arrays(): void
    {
        $compiler = app(AutomationConfigCompiler::class);
        $method = new \ReflectionMethod($compiler, 'deepMerge');

        $base = ['items' => [1, 2, 3]];
        $override = ['items' => [4, 5]];

        $result = $method->invoke($compiler, $base, $override);

        $this->assertEquals([4, 5], $result['items']);
    }

    public function test_deep_merge_adds_new_keys(): void
    {
        $compiler = app(AutomationConfigCompiler::class);
        $method = new \ReflectionMethod($compiler, 'deepMerge');

        $base = ['existing' => 1];
        $override = ['new_key' => 'added'];

        $result = $method->invoke($compiler, $base, $override);

        $this->assertEquals(1, $result['existing']);
        $this->assertEquals('added', $result['new_key']);
    }

    // --- GrowCycleService integration ---

    public function test_sync_cycle_config_documents_saves_config_overrides(): void
    {
        [$zone, $cycle] = $this->setupZoneWithCycle();

        app(\App\Services\GrowCycleService::class)->syncCycleConfigDocuments($cycle, [
            'config_overrides' => [
                'logic_profile' => ['active_mode' => 'test_override'],
            ],
        ]);

        $doc = AutomationConfigDocument::query()
            ->where('namespace', AutomationConfigRegistry::NAMESPACE_CYCLE_CONFIG_OVERRIDES)
            ->where('scope_type', AutomationConfigRegistry::SCOPE_GROW_CYCLE)
            ->where('scope_id', $cycle->id)
            ->first();

        $this->assertNotNull($doc);
        $this->assertEquals('test_override', data_get($doc->payload, 'logic_profile.active_mode'));
    }

    public function test_sync_cycle_config_documents_does_not_write_overrides_for_empty_data(): void
    {
        [$zone, $cycle] = $this->setupZoneWithCycle();

        // Delete any pre-existing config_overrides document
        AutomationConfigDocument::query()
            ->where('namespace', AutomationConfigRegistry::NAMESPACE_CYCLE_CONFIG_OVERRIDES)
            ->where('scope_type', AutomationConfigRegistry::SCOPE_GROW_CYCLE)
            ->where('scope_id', $cycle->id)
            ->delete();

        app(\App\Services\GrowCycleService::class)->syncCycleConfigDocuments($cycle, []);

        $doc = AutomationConfigDocument::query()
            ->where('namespace', AutomationConfigRegistry::NAMESPACE_CYCLE_CONFIG_OVERRIDES)
            ->where('scope_type', AutomationConfigRegistry::SCOPE_GROW_CYCLE)
            ->where('scope_id', $cycle->id)
            ->first();

        $this->assertNull($doc);
    }

    public function test_sync_cycle_config_documents_does_not_write_overrides_for_null(): void
    {
        [$zone, $cycle] = $this->setupZoneWithCycle();

        // Delete any pre-existing config_overrides document
        AutomationConfigDocument::query()
            ->where('namespace', AutomationConfigRegistry::NAMESPACE_CYCLE_CONFIG_OVERRIDES)
            ->where('scope_type', AutomationConfigRegistry::SCOPE_GROW_CYCLE)
            ->where('scope_id', $cycle->id)
            ->delete();

        app(\App\Services\GrowCycleService::class)->syncCycleConfigDocuments($cycle, [
            'config_overrides' => null,
        ]);

        $doc = AutomationConfigDocument::query()
            ->where('namespace', AutomationConfigRegistry::NAMESPACE_CYCLE_CONFIG_OVERRIDES)
            ->where('scope_type', AutomationConfigRegistry::SCOPE_GROW_CYCLE)
            ->where('scope_id', $cycle->id)
            ->first();

        $this->assertNull($doc);
    }
}
