<?php

namespace Tests\Unit\Services;

use App\Models\Alert;
use App\Models\AutomationEffectiveBundle;
use App\Models\AutomationConfigPreset;
use App\Models\GrowCycle;
use App\Models\GrowCyclePhase;
use App\Models\Recipe;
use App\Models\RecipeRevision;
use App\Models\RecipeRevisionPhase;
use App\Models\Zone;
use App\Services\AutomationConfigCompiler;
use App\Services\AutomationConfigDocumentService;
use App\Services\AutomationConfigRegistry;
use App\Services\ZoneCorrectionConfigCatalog;
use App\Support\Automation\RecipeNutritionRuntimeConfigResolver;
use App\Support\Automation\ZoneProcessCalibrationDefaults;
use App\Enums\GrowCycleStatus;
use Tests\RefreshDatabase;
use Tests\TestCase;

class AutomationConfigDocumentServiceTest extends TestCase
{
    use RefreshDatabase;

    public function test_ensure_zone_defaults_bootstraps_zone_correction_and_resolves_missing_alert(): void
    {
        $documents = app(AutomationConfigDocumentService::class);
        $zone = Zone::factory()->create();

        $documents->upsertDocument(
            AutomationConfigRegistry::NAMESPACE_SYSTEM_ALERT_POLICIES,
            AutomationConfigRegistry::SCOPE_SYSTEM,
            0,
            [
                'ae3_operational_resolution_mode' => 'auto_resolve_on_recovery',
            ]
        );

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

        $documents->ensureZoneDefaults($zone->id);

        $payload = $documents->getPayload(
            AutomationConfigRegistry::NAMESPACE_ZONE_CORRECTION,
            AutomationConfigRegistry::SCOPE_ZONE,
            $zone->id
        );

        $this->assertSame('irrig', data_get($payload, 'base_config.runtime.required_node_type'));
        $this->assertSame(50, data_get($payload, 'resolved_config.pump_calibration.min_dose_ms'));
        $this->assertDatabaseHas('automation_config_documents', [
            'namespace' => AutomationConfigRegistry::NAMESPACE_ZONE_CORRECTION,
            'scope_type' => AutomationConfigRegistry::SCOPE_ZONE,
            'scope_id' => $zone->id,
            'source' => 'bootstrap',
        ]);
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

    public function test_zone_correction_normalizer_uses_current_system_pump_calibration_policy(): void
    {
        $documents = app(AutomationConfigDocumentService::class);
        $zone = Zone::factory()->create();

        $documents->upsertDocument(
            AutomationConfigRegistry::NAMESPACE_SYSTEM_PUMP_CALIBRATION_POLICY,
            AutomationConfigRegistry::SCOPE_SYSTEM,
            0,
            [
                'ml_per_sec_min' => 0.02,
                'ml_per_sec_max' => 12.5,
                'min_dose_ms' => 125,
                'calibration_duration_min_sec' => 2,
                'calibration_duration_max_sec' => 90,
                'quality_score_basic' => 0.70,
                'quality_score_with_k' => 0.90,
                'quality_score_legacy' => 0.50,
                'age_warning_days' => 20,
                'age_critical_days' => 60,
                'default_run_duration_sec' => 15,
            ]
        );

        $documents->upsertDocument(
            AutomationConfigRegistry::NAMESPACE_ZONE_CORRECTION,
            AutomationConfigRegistry::SCOPE_ZONE,
            $zone->id,
            [
                'preset_id' => null,
                'base_config' => ZoneCorrectionConfigCatalog::defaults(),
                'phase_overrides' => [],
            ]
        );

        $payload = $documents->getPayload(
            AutomationConfigRegistry::NAMESPACE_ZONE_CORRECTION,
            AutomationConfigRegistry::SCOPE_ZONE,
            $zone->id
        );

        $this->assertSame(125, data_get($payload, 'resolved_config.pump_calibration.min_dose_ms'));
        $this->assertSame(0.02, data_get($payload, 'resolved_config.pump_calibration.ml_per_sec_min'));
        $this->assertSame(12.5, data_get($payload, 'resolved_config.pump_calibration.ml_per_sec_max'));
    }

    public function test_zone_correction_normalizer_applies_preset_to_resolved_config(): void
    {
        $documents = app(AutomationConfigDocumentService::class);
        $zone = Zone::factory()->create();
        $preset = AutomationConfigPreset::query()->create([
            'namespace' => AutomationConfigRegistry::NAMESPACE_ZONE_CORRECTION,
            'scope' => 'system',
            'is_locked' => false,
            'name' => 'Correction preset',
            'slug' => 'correction-preset',
            'description' => 'test',
            'schema_version' => 1,
            'payload' => [
                'base' => [
                    'timing' => [
                        'stabilization_sec' => 321,
                    ],
                ],
                'phases' => [],
            ],
            'updated_by' => null,
        ]);

        $documents->upsertDocument(
            AutomationConfigRegistry::NAMESPACE_ZONE_CORRECTION,
            AutomationConfigRegistry::SCOPE_ZONE,
            $zone->id,
            [
                'preset_id' => $preset->id,
                'base_config' => ZoneCorrectionConfigCatalog::defaults(),
                'phase_overrides' => [],
            ]
        );

        $payload = $documents->getPayload(
            AutomationConfigRegistry::NAMESPACE_ZONE_CORRECTION,
            AutomationConfigRegistry::SCOPE_ZONE,
            $zone->id
        );

        $this->assertSame($preset->id, data_get($payload, 'resolved_config.meta.preset_id'));
        $this->assertSame('correction-preset', data_get($payload, 'resolved_config.meta.preset_slug'));
        $this->assertSame('Correction preset', data_get($payload, 'resolved_config.meta.preset_name'));
    }

    public function test_zone_correction_bundle_uses_current_document_revision_in_meta_version(): void
    {
        $documents = app(AutomationConfigDocumentService::class);
        $zone = Zone::factory()->create();

        $documents->ensureZoneDefaults($zone->id);

        /** @var AutomationEffectiveBundle $bundle */
        $bundle = AutomationEffectiveBundle::query()
            ->where('scope_type', AutomationConfigRegistry::SCOPE_ZONE)
            ->where('scope_id', $zone->id)
            ->firstOrFail();

        $this->assertSame(1, data_get($bundle->config, 'zone.correction.resolved_config.meta.version'));

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

        $bundle = AutomationEffectiveBundle::query()
            ->where('scope_type', AutomationConfigRegistry::SCOPE_ZONE)
            ->where('scope_id', $zone->id)
            ->firstOrFail();

        $this->assertSame(2, data_get($bundle->config, 'zone.correction.resolved_config.meta.version'));
    }

    public function test_ensure_zone_defaults_bootstraps_phase_specific_process_calibration_defaults(): void
    {
        $documents = app(AutomationConfigDocumentService::class);
        $zone = Zone::factory()->create();

        $documents->ensureZoneDefaults($zone->id);

        foreach ([
            'generic' => AutomationConfigRegistry::NAMESPACE_ZONE_PROCESS_CALIBRATION_GENERIC,
            'solution_fill' => AutomationConfigRegistry::NAMESPACE_ZONE_PROCESS_CALIBRATION_SOLUTION_FILL,
            'tank_recirc' => AutomationConfigRegistry::NAMESPACE_ZONE_PROCESS_CALIBRATION_TANK_RECIRC,
            'irrigation' => AutomationConfigRegistry::NAMESPACE_ZONE_PROCESS_CALIBRATION_IRRIGATION,
        ] as $mode => $namespace) {
            $payload = $documents->getPayload($namespace, AutomationConfigRegistry::SCOPE_ZONE, $zone->id);
            $expected = ZoneProcessCalibrationDefaults::forMode($mode);

            $this->assertSame($mode, $payload['mode']);
            $this->assertSame('system_default', $payload['source']);
            $this->assertSame($expected['ec_gain_per_ml'], $payload['ec_gain_per_ml']);
            $this->assertSame($expected['ph_up_gain_per_ml'], $payload['ph_up_gain_per_ml']);
            $this->assertSame($expected['ph_down_gain_per_ml'], $payload['ph_down_gain_per_ml']);
            $this->assertSame($expected['transport_delay_sec'], $payload['transport_delay_sec']);
            $this->assertSame($expected['settle_sec'], $payload['settle_sec']);
        }
    }

    public function test_compiler_applies_recipe_derived_inline_ec_config_to_grow_cycle_bundle(): void
    {
        $documents = app(AutomationConfigDocumentService::class);
        $compiler = app(AutomationConfigCompiler::class);
        $zone = Zone::factory()->create();
        $recipe = Recipe::factory()->create();
        $revision = RecipeRevision::factory()->create([
            'recipe_id' => $recipe->id,
            'status' => 'PUBLISHED',
        ]);
        $recipePhase = RecipeRevisionPhase::factory()->create([
            'recipe_revision_id' => $revision->id,
            'phase_index' => 0,
            'name' => 'Inline EC',
            'nutrient_mode' => 'ratio_ec_pid',
            'nutrient_solution_volume_l' => 135.0,
            'nutrient_npk_ratio_pct' => 44.0,
            'nutrient_calcium_ratio_pct' => 36.0,
            'nutrient_magnesium_ratio_pct' => 17.0,
            'nutrient_micro_ratio_pct' => 3.0,
        ]);
        $cycle = GrowCycle::factory()->create([
            'zone_id' => $zone->id,
            'recipe_revision_id' => $revision->id,
            'status' => GrowCycleStatus::RUNNING,
        ]);
        $snapshotPhase = GrowCyclePhase::factory()->create([
            'grow_cycle_id' => $cycle->id,
            'recipe_revision_phase_id' => $recipePhase->id,
            'phase_index' => 0,
            'name' => 'Inline EC',
            'nutrient_mode' => 'ratio_ec_pid',
            'nutrient_solution_volume_l' => 135.0,
            'nutrient_npk_ratio_pct' => 44.0,
            'nutrient_calcium_ratio_pct' => 36.0,
            'nutrient_magnesium_ratio_pct' => 17.0,
            'nutrient_micro_ratio_pct' => 3.0,
        ]);
        $cycle->update(['current_phase_id' => $snapshotPhase->id]);

        $documents->ensureZoneDefaults($zone->id);
        $documents->ensureCycleDefaults($cycle->id);

        $bundle = $compiler->compileGrowCycleBundle($cycle->id);

        $this->assertSame(
            'multi_sequential',
            data_get($bundle->config, 'zone.correction.resolved_config.phases.irrigation.ec_dosing_mode')
        );
        $this->assertSame(
            ['npk'],
            data_get($bundle->config, 'zone.correction.resolved_config.phases.irrigation.ec_excluded_components')
        );
        $this->assertEquals(
            135.0,
            data_get($bundle->config, 'zone.correction.resolved_config.base.dosing.solution_volume_l')
        );
        $this->assertEquals(
            36.0,
            data_get($bundle->config, 'zone.correction.resolved_config.phases.irrigation.ec_component_policy.irrigation.calcium')
        );
        $this->assertSame(
            'ratio_ec_pid',
            data_get($bundle->config, 'zone.correction.resolved_config.meta.recipe_nutrient_mode')
        );
    }

    public function test_recipe_nutrition_runtime_resolver_supports_delta_ec_by_k_without_frontend_hardcode(): void
    {
        $resolver = app(RecipeNutritionRuntimeConfigResolver::class);

        $resolved = $resolver->applyToResolvedConfig(
            [
                'base' => ZoneCorrectionConfigCatalog::defaults(),
                'phases' => [
                    'solution_fill' => ZoneCorrectionConfigCatalog::defaults(),
                    'tank_recirc' => ZoneCorrectionConfigCatalog::defaults(),
                    'irrigation' => ZoneCorrectionConfigCatalog::defaults(),
                ],
                'meta' => [],
            ],
            [
                'mode' => 'delta_ec_by_k',
                'solution_volume_l' => 110.0,
                'components' => [
                    'npk' => ['ratio_pct' => 45.0],
                    'calcium' => ['ratio_pct' => 33.0],
                    'magnesium' => ['ratio_pct' => 17.0],
                    'micro' => ['ratio_pct' => 5.0],
                ],
            ]
        );

        $this->assertSame('delta_ec_by_k', data_get($resolved, 'meta.recipe_nutrient_mode'));
        $this->assertSame('multi_sequential', data_get($resolved, 'phases.irrigation.ec_dosing_mode'));
        $this->assertSame(110.0, data_get($resolved, 'base.dosing.solution_volume_l'));
        $this->assertSame(
            ['npk'],
            data_get($resolved, 'phases.irrigation.ec_excluded_components')
        );
        $this->assertSame(
            5.0,
            data_get($resolved, 'phases.irrigation.ec_component_policy.irrigation.micro')
        );
    }
}
