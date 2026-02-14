<?php

namespace Tests\Unit;

use App\Models\GrowCycle;
use App\Models\GrowCyclePhase;
use App\Models\GrowCycleOverride;
use App\Models\Recipe;
use App\Models\RecipeRevision;
use App\Models\RecipeRevisionPhase;
use App\Models\NutrientProduct;
use App\Models\Zone;
use App\Models\ZoneAutomationLogicProfile;
use App\Services\EffectiveTargetsService;
use App\Enums\GrowCycleStatus;
use Tests\RefreshDatabase;
use PHPUnit\Framework\Attributes\Test;
use Tests\TestCase;

class EffectiveTargetsServiceTest extends TestCase
{
    use RefreshDatabase;

    private EffectiveTargetsService $service;

    protected function setUp(): void
    {
        parent::setUp();
        $this->service = app(EffectiveTargetsService::class);
    }

    #[Test]
    public function it_returns_effective_targets_with_correct_structure()
    {
        $zone = Zone::factory()->create();
        $recipe = Recipe::factory()->create();
        $revision = RecipeRevision::factory()->create([
            'recipe_id' => $recipe->id,
            'status' => 'PUBLISHED',
        ]);

        $phase = RecipeRevisionPhase::factory()->create([
            'recipe_revision_id' => $revision->id,
            'phase_index' => 0,
            'name' => 'Test Phase',
            'ph_target' => 6.0,
            'ph_min' => 5.8,
            'ph_max' => 6.2,
            'ec_target' => 1.5,
            'ec_min' => 1.3,
            'ec_max' => 1.7,
            'irrigation_mode' => 'SUBSTRATE',
            'irrigation_interval_sec' => 3600,
            'irrigation_duration_sec' => 300,
        ]);

        $cycle = GrowCycle::factory()->create([
            'zone_id' => $zone->id,
            'recipe_revision_id' => $revision->id,
            'status' => GrowCycleStatus::RUNNING,
        ]);

        // Создаем снапшот фазы
        $snapshotPhase = GrowCyclePhase::factory()->create([
            'grow_cycle_id' => $cycle->id,
            'recipe_revision_phase_id' => $phase->id,
            'phase_index' => 0,
            'name' => 'Test Phase',
            'ph_target' => 6.0,
            'ph_min' => 5.8,
            'ph_max' => 6.2,
            'ec_target' => 1.5,
            'ec_min' => 1.3,
            'ec_max' => 1.7,
        ]);

        $cycle->update(['current_phase_id' => $snapshotPhase->id]);

        $result = $this->service->getEffectiveTargets($cycle->id);

        // Проверяем структуру ответа
        $this->assertArrayHasKey('cycle_id', $result);
        $this->assertArrayHasKey('zone_id', $result);
        $this->assertArrayHasKey('phase', $result);
        $this->assertArrayHasKey('targets', $result);

        // Проверяем структуру phase
        $this->assertArrayHasKey('id', $result['phase']);
        $this->assertArrayHasKey('name', $result['phase']);
        $this->assertArrayHasKey('started_at', $result['phase']);
        $this->assertArrayHasKey('due_at', $result['phase']);

        // Проверяем структуру targets
        $this->assertArrayHasKey('ph', $result['targets']);
        $this->assertArrayHasKey('ec', $result['targets']);

        // Проверяем структуру ph
        $this->assertArrayHasKey('target', $result['targets']['ph']);
        $this->assertArrayHasKey('min', $result['targets']['ph']);
        $this->assertArrayHasKey('max', $result['targets']['ph']);

        // Проверяем значения
        $this->assertEquals(6.0, $result['targets']['ph']['target']);
        $this->assertEquals(5.8, $result['targets']['ph']['min']);
        $this->assertEquals(6.2, $result['targets']['ph']['max']);
    }

    #[Test]
    public function it_applies_overrides_to_targets()
    {
        $zone = Zone::factory()->create();
        $recipe = Recipe::factory()->create();
        $revision = RecipeRevision::factory()->create([
            'recipe_id' => $recipe->id,
            'status' => 'PUBLISHED',
        ]);

        $phase = RecipeRevisionPhase::factory()->create([
            'recipe_revision_id' => $revision->id,
            'phase_index' => 0,
            'name' => 'Test Phase',
            'ph_target' => 6.0,
            'ph_min' => 5.8,
            'ph_max' => 6.2,
        ]);

        $cycle = GrowCycle::factory()->create([
            'zone_id' => $zone->id,
            'recipe_revision_id' => $revision->id,
            'status' => GrowCycleStatus::RUNNING,
        ]);

        $snapshotPhase = GrowCyclePhase::factory()->create([
            'grow_cycle_id' => $cycle->id,
            'recipe_revision_phase_id' => $phase->id,
            'phase_index' => 0,
            'name' => 'Test Phase',
            'ph_target' => 6.0,
            'ph_min' => 5.8,
            'ph_max' => 6.2,
        ]);

        $cycle->update(['current_phase_id' => $snapshotPhase->id]);

        // Создаем override для pH (используем точечную нотацию для вложенных параметров)
        GrowCycleOverride::factory()->create([
            'grow_cycle_id' => $cycle->id,
            'parameter' => 'ph.target',
            'value' => '6.5',
            'value_type' => 'decimal',
            'is_active' => true,
            'applies_from' => now()->subDay(),
            'applies_until' => null,
        ]);

        $result = $this->service->getEffectiveTargets($cycle->id);

        // Проверяем, что override применен
        $this->assertEquals(6.5, $result['targets']['ph']['target']);
        // min и max остаются из фазы
        $this->assertEquals(5.8, $result['targets']['ph']['min']);
        $this->assertEquals(6.2, $result['targets']['ph']['max']);
    }

    #[Test]
    public function it_returns_batch_results_for_multiple_cycles()
    {
        $zone1 = Zone::factory()->create();
        $zone2 = Zone::factory()->create();
        $recipe = Recipe::factory()->create();
        $revision = RecipeRevision::factory()->create([
            'recipe_id' => $recipe->id,
            'status' => 'PUBLISHED',
        ]);

        $phase = RecipeRevisionPhase::factory()->create([
            'recipe_revision_id' => $revision->id,
            'phase_index' => 0,
            'name' => 'Test Phase',
            'ph_target' => 6.0,
        ]);

        $cycle1 = GrowCycle::factory()->create([
            'zone_id' => $zone1->id,
            'recipe_revision_id' => $revision->id,
            'status' => GrowCycleStatus::RUNNING,
        ]);

        $cycle2 = GrowCycle::factory()->create([
            'zone_id' => $zone2->id,
            'recipe_revision_id' => $revision->id,
            'status' => GrowCycleStatus::RUNNING,
        ]);

        $snapshotPhase1 = GrowCyclePhase::factory()->create([
            'grow_cycle_id' => $cycle1->id,
            'recipe_revision_phase_id' => $phase->id,
            'phase_index' => 0,
            'name' => 'Test Phase',
            'ph_target' => 6.0,
        ]);

        $snapshotPhase2 = GrowCyclePhase::factory()->create([
            'grow_cycle_id' => $cycle2->id,
            'recipe_revision_phase_id' => $phase->id,
            'phase_index' => 0,
            'name' => 'Test Phase',
            'ph_target' => 6.0,
        ]);

        $cycle1->update(['current_phase_id' => $snapshotPhase1->id]);
        $cycle2->update(['current_phase_id' => $snapshotPhase2->id]);

        $results = $this->service->getEffectiveTargetsBatch([$cycle1->id, $cycle2->id]);

        $this->assertCount(2, $results);
        $this->assertArrayHasKey($cycle1->id, $results);
        $this->assertArrayHasKey($cycle2->id, $results);
        $this->assertArrayHasKey('targets', $results[$cycle1->id]);
        $this->assertArrayHasKey('targets', $results[$cycle2->id]);
    }

    #[Test]
    public function it_handles_missing_current_phase_gracefully()
    {
        $zone = Zone::factory()->create();
        $recipe = Recipe::factory()->create();
        $revision = RecipeRevision::factory()->create([
            'recipe_id' => $recipe->id,
            'status' => 'PUBLISHED',
        ]);

        $cycle = GrowCycle::factory()->create([
            'zone_id' => $zone->id,
            'recipe_revision_id' => $revision->id,
            'status' => GrowCycleStatus::RUNNING,
            'current_phase_id' => null,
        ]);

        $this->expectException(\RuntimeException::class);
        $this->expectExceptionMessage("Grow cycle {$cycle->id} has no current phase");

        $this->service->getEffectiveTargets($cycle->id);
    }

    #[Test]
    public function it_includes_irrigation_targets_in_response()
    {
        $zone = Zone::factory()->create();
        $recipe = Recipe::factory()->create();
        $revision = RecipeRevision::factory()->create([
            'recipe_id' => $recipe->id,
            'status' => 'PUBLISHED',
        ]);

        $phase = RecipeRevisionPhase::factory()->create([
            'recipe_revision_id' => $revision->id,
            'phase_index' => 0,
            'name' => 'Test Phase',
            'irrigation_mode' => 'SUBSTRATE',
            'irrigation_interval_sec' => 3600,
            'irrigation_duration_sec' => 300,
        ]);

        $cycle = GrowCycle::factory()->create([
            'zone_id' => $zone->id,
            'recipe_revision_id' => $revision->id,
            'status' => GrowCycleStatus::RUNNING,
        ]);

        $snapshotPhase = GrowCyclePhase::factory()->create([
            'grow_cycle_id' => $cycle->id,
            'recipe_revision_phase_id' => $phase->id,
            'phase_index' => 0,
            'name' => 'Test Phase',
            'irrigation_mode' => 'SUBSTRATE',
            'irrigation_interval_sec' => 3600,
            'irrigation_duration_sec' => 300,
        ]);

        $cycle->update(['current_phase_id' => $snapshotPhase->id]);

        $result = $this->service->getEffectiveTargets($cycle->id);

        $this->assertArrayHasKey('irrigation', $result['targets']);
        $this->assertEquals('SUBSTRATE', $result['targets']['irrigation']['mode']);
        $this->assertEquals(3600, $result['targets']['irrigation']['interval_sec']);
        $this->assertEquals(300, $result['targets']['irrigation']['duration_sec']);
    }

    #[Test]
    public function it_merges_runtime_subsystems_into_effective_targets()
    {
        $zone = Zone::factory()->create();
        $recipe = Recipe::factory()->create();
        $revision = RecipeRevision::factory()->create([
            'recipe_id' => $recipe->id,
            'status' => 'PUBLISHED',
        ]);

        $phase = RecipeRevisionPhase::factory()->create([
            'recipe_revision_id' => $revision->id,
            'phase_index' => 0,
            'name' => 'Runtime Merge',
            'ph_target' => 6.0,
            'ec_target' => 1.6,
            'irrigation_mode' => 'SUBSTRATE',
            'irrigation_interval_sec' => 3600,
            'irrigation_duration_sec' => 300,
            'lighting_photoperiod_hours' => 16,
            'lighting_start_time' => '06:00:00',
            'temp_air_target' => 23,
            'humidity_target' => 62,
        ]);

        $cycle = GrowCycle::factory()->create([
            'zone_id' => $zone->id,
            'recipe_revision_id' => $revision->id,
            'status' => GrowCycleStatus::RUNNING,
        ]);

        ZoneAutomationLogicProfile::query()->create([
            'zone_id' => $zone->id,
            'mode' => ZoneAutomationLogicProfile::MODE_WORKING,
            'is_active' => true,
            'subsystems' => [
                'ph' => [
                    'enabled' => true,
                    'execution' => [
                        'target' => 5.4,
                        'min' => 5.2,
                        'max' => 5.6,
                    ],
                ],
                'ec' => [
                    'enabled' => true,
                    'execution' => [
                        'target' => 2.4,
                        'min' => 2.1,
                        'max' => 2.7,
                    ],
                ],
                'irrigation' => [
                    'enabled' => true,
                    'execution' => [
                        'interval_minutes' => 20,
                        'duration_seconds' => 45,
                        'system_type' => 'nft',
                    ],
                ],
                'lighting' => [
                    'enabled' => false,
                    'execution' => [
                        'photoperiod' => ['hours_on' => 10],
                        'schedule' => [['start' => '08:00', 'end' => '18:00']],
                        'interval_minutes' => 120,
                    ],
                ],
                'climate' => [
                    'enabled' => false,
                    'execution' => [
                        'temperature' => ['day' => 24],
                        'humidity' => ['day' => 64],
                        'interval_minutes' => 15,
                    ],
                ],
                'diagnostics' => [
                    'enabled' => true,
                    'execution' => [
                        'interval_minutes' => 30,
                        'topology' => 'two_tank_drip_substrate_trays',
                        'workflow' => 'cycle_start',
                        'required_node_types' => ['irrig', 'climate'],
                        'clean_tank_full_threshold' => 0.9,
                        'refill_duration_sec' => 40,
                        'refill_timeout_sec' => 600,
                        'startup' => [
                            'clean_fill_timeout_sec' => 1200,
                            'solution_fill_timeout_sec' => 1800,
                            'level_poll_interval_sec' => 60,
                            'clean_fill_retry_cycles' => 1,
                            'prepare_recirculation_timeout_sec' => 1200,
                        ],
                        'dosing_rules' => [
                            'prepare_allowed_components' => ['npk'],
                        ],
                        'refill' => [
                            'channel' => 'fill_valve',
                        ],
                    ],
                ],
                'solution_change' => [
                    'enabled' => true,
                    'execution' => [
                        'interval_minutes' => 180,
                        'duration_seconds' => 120,
                    ],
                ],
            ],
        ]);

        $snapshotPhase = GrowCyclePhase::factory()->create([
            'grow_cycle_id' => $cycle->id,
            'recipe_revision_phase_id' => $phase->id,
            'phase_index' => 0,
            'name' => 'Runtime Merge',
            'ph_target' => 6.0,
            'ec_target' => 1.6,
            'irrigation_mode' => 'SUBSTRATE',
            'irrigation_interval_sec' => 3600,
            'irrigation_duration_sec' => 300,
            'lighting_photoperiod_hours' => 16,
            'lighting_start_time' => '06:00:00',
            'temp_air_target' => 23,
            'humidity_target' => 62,
        ]);
        $cycle->update(['current_phase_id' => $snapshotPhase->id]);

        $result = $this->service->getEffectiveTargets($cycle->id);

        $this->assertSame(6.0, $result['targets']['ph']['target']);
        $this->assertSame(1.6, $result['targets']['ec']['target']);

        $this->assertSame(1200, $result['targets']['irrigation']['interval_sec']);
        $this->assertSame(45, $result['targets']['irrigation']['duration_sec']);
        $this->assertSame('nft', $result['targets']['irrigation']['system_type']);

        $this->assertSame(10.0, $result['targets']['lighting']['photoperiod_hours']);
        $this->assertSame('08:00', $result['targets']['lighting']['start_time']);
        $this->assertSame(7200, $result['targets']['lighting']['interval_sec']);
        $this->assertTrue($result['targets']['lighting']['execution']['force_skip']);

        $this->assertSame(24.0, $result['targets']['climate_request']['temp_air_target']);
        $this->assertSame(64.0, $result['targets']['climate_request']['humidity_target']);
        $this->assertSame(900, $result['targets']['ventilation']['interval_sec']);
        $this->assertTrue($result['targets']['ventilation']['execution']['force_skip']);

        $this->assertSame(1800, $result['targets']['diagnostics']['interval_sec']);
        $this->assertSame('two_tank_drip_substrate_trays', $result['targets']['diagnostics']['execution']['topology']);
        $this->assertSame('cycle_start', $result['targets']['diagnostics']['execution']['workflow']);
        $this->assertSame(0.9, $result['targets']['diagnostics']['execution']['clean_tank_full_threshold']);
        $this->assertSame(40, $result['targets']['diagnostics']['execution']['refill_duration_sec']);
        $this->assertSame(600, $result['targets']['diagnostics']['execution']['refill_timeout_sec']);
        $this->assertSame(1200, $result['targets']['diagnostics']['execution']['startup']['clean_fill_timeout_sec']);
        $this->assertSame(1800, $result['targets']['diagnostics']['execution']['startup']['solution_fill_timeout_sec']);
        $this->assertSame(60, $result['targets']['diagnostics']['execution']['startup']['level_poll_interval_sec']);
        $this->assertSame(1, $result['targets']['diagnostics']['execution']['startup']['clean_fill_retry_cycles']);
        $this->assertSame(1200, $result['targets']['diagnostics']['execution']['startup']['prepare_recirculation_timeout_sec']);
        $this->assertSame(['npk'], $result['targets']['diagnostics']['execution']['dosing_rules']['prepare_allowed_components']);
        $this->assertSame('fill_valve', $result['targets']['diagnostics']['execution']['refill']['channel']);

        $this->assertSame(10800, $result['targets']['solution_change']['interval_sec']);
        $this->assertSame(120, $result['targets']['solution_change']['duration_sec']);

        $this->assertSame(
            20,
            data_get($result, 'targets.extensions.subsystems.irrigation.execution.interval_minutes')
        );
    }

    #[Test]
    public function it_ignores_legacy_cycle_settings_subsystems_when_runtime_profile_is_absent(): void
    {
        $zone = Zone::factory()->create();
        $recipe = Recipe::factory()->create();
        $revision = RecipeRevision::factory()->create([
            'recipe_id' => $recipe->id,
            'status' => 'PUBLISHED',
        ]);

        $phase = RecipeRevisionPhase::factory()->create([
            'recipe_revision_id' => $revision->id,
            'phase_index' => 0,
            'name' => 'Profile priority',
            'ph_target' => 6.0,
            'ec_target' => 1.6,
            'irrigation_mode' => 'SUBSTRATE',
            'irrigation_interval_sec' => 3600,
            'irrigation_duration_sec' => 300,
        ]);

        $cycle = GrowCycle::factory()->create([
            'zone_id' => $zone->id,
            'recipe_revision_id' => $revision->id,
            'status' => GrowCycleStatus::RUNNING,
            'settings' => [
                'subsystems' => [
                    'ph' => [
                        'enabled' => true,
                        'targets' => ['target' => 6.9],
                    ],
                    'ec' => [
                        'enabled' => true,
                        'targets' => ['target' => 2.8],
                    ],
                    'irrigation' => [
                        'enabled' => true,
                        'targets' => [
                            'interval_minutes' => 99,
                            'duration_seconds' => 99,
                        ],
                    ],
                ],
            ],
        ]);

        $snapshotPhase = GrowCyclePhase::factory()->create([
            'grow_cycle_id' => $cycle->id,
            'recipe_revision_phase_id' => $phase->id,
            'phase_index' => 0,
            'name' => 'Profile priority',
            'ph_target' => 6.0,
            'ec_target' => 1.6,
            'irrigation_mode' => 'SUBSTRATE',
            'irrigation_interval_sec' => 3600,
            'irrigation_duration_sec' => 300,
        ]);
        $cycle->update(['current_phase_id' => $snapshotPhase->id]);

        $result = $this->service->getEffectiveTargets($cycle->id);

        // Legacy cycle.settings.subsystems больше не участвует в runtime merge
        $this->assertSame(6.0, data_get($result, 'targets.ph.target'));
        $this->assertSame(1.6, data_get($result, 'targets.ec.target'));
        $this->assertSame(3600, data_get($result, 'targets.irrigation.interval_sec'));
        $this->assertSame(300, data_get($result, 'targets.irrigation.duration_sec'));
        $this->assertNull(data_get($result, 'targets.extensions.automation_logic.source'));
    }

    #[Test]
    public function it_applies_runtime_only_from_active_profile_mode(): void
    {
        $zone = Zone::factory()->create();
        $recipe = Recipe::factory()->create();
        $revision = RecipeRevision::factory()->create([
            'recipe_id' => $recipe->id,
            'status' => 'PUBLISHED',
        ]);

        $phase = RecipeRevisionPhase::factory()->create([
            'recipe_revision_id' => $revision->id,
            'phase_index' => 0,
            'name' => 'Active mode only',
            'ph_target' => 6.1,
            'ec_target' => 1.5,
        ]);

        $cycle = GrowCycle::factory()->create([
            'zone_id' => $zone->id,
            'recipe_revision_id' => $revision->id,
            'status' => GrowCycleStatus::RUNNING,
        ]);

        ZoneAutomationLogicProfile::query()->create([
            'zone_id' => $zone->id,
            'mode' => ZoneAutomationLogicProfile::MODE_WORKING,
            'is_active' => false,
            'subsystems' => [
                'ph' => [
                    'enabled' => true,
                    'execution' => [
                        'target' => 5.4,
                    ],
                ],
                'ec' => [
                    'enabled' => true,
                    'execution' => [
                        'target' => 2.3,
                    ],
                ],
                'irrigation' => [
                    'enabled' => true,
                    'execution' => [
                        'interval_minutes' => 10,
                        'duration_seconds' => 15,
                    ],
                ],
            ],
        ]);

        $snapshotPhase = GrowCyclePhase::factory()->create([
            'grow_cycle_id' => $cycle->id,
            'recipe_revision_phase_id' => $phase->id,
            'phase_index' => 0,
            'name' => 'Active mode only',
            'ph_target' => 6.1,
            'ec_target' => 1.5,
        ]);
        $cycle->update(['current_phase_id' => $snapshotPhase->id]);

        $result = $this->service->getEffectiveTargets($cycle->id);

        $this->assertSame(6.1, data_get($result, 'targets.ph.target'));
        $this->assertSame(1.5, data_get($result, 'targets.ec.target'));
        $this->assertNull(data_get($result, 'targets.extensions.automation_logic.source'));
    }

    #[Test]
    public function it_clears_force_skip_when_runtime_subsystem_is_enabled(): void
    {
        $zone = Zone::factory()->create();
        $recipe = Recipe::factory()->create();
        $revision = RecipeRevision::factory()->create([
            'recipe_id' => $recipe->id,
            'status' => 'PUBLISHED',
        ]);

        $phase = RecipeRevisionPhase::factory()->create([
            'recipe_revision_id' => $revision->id,
            'phase_index' => 0,
            'name' => 'Force skip reset',
            'lighting_photoperiod_hours' => 16,
            'lighting_start_time' => '06:00:00',
            'extensions' => [
                'scheduler' => 'legacy',
            ],
        ]);

        $cycle = GrowCycle::factory()->create([
            'zone_id' => $zone->id,
            'recipe_revision_id' => $revision->id,
            'status' => GrowCycleStatus::RUNNING,
        ]);

        ZoneAutomationLogicProfile::query()->create([
            'zone_id' => $zone->id,
            'mode' => ZoneAutomationLogicProfile::MODE_WORKING,
            'is_active' => true,
            'subsystems' => [
                'lighting' => [
                    'enabled' => true,
                    'execution' => [
                        'force_skip' => false,
                    ],
                ],
            ],
        ]);

        $snapshotPhase = GrowCyclePhase::factory()->create([
            'grow_cycle_id' => $cycle->id,
            'recipe_revision_phase_id' => $phase->id,
            'phase_index' => 0,
            'name' => 'Force skip reset',
            'lighting_photoperiod_hours' => 16,
            'lighting_start_time' => '06:00:00',
        ]);
        $cycle->update(['current_phase_id' => $snapshotPhase->id]);

        $result = $this->service->getEffectiveTargets($cycle->id);

        $this->assertArrayHasKey('lighting', $result['targets']);
        $this->assertArrayHasKey('execution', $result['targets']['lighting']);
        $this->assertFalse($result['targets']['lighting']['execution']['force_skip']);
        $this->assertSame(
            true,
            isset($result['targets']['extensions']['subsystems']['lighting'])
        );
    }

    #[Test]
    public function it_includes_nutrition_targets_for_four_component_feeding()
    {
        $npk = NutrientProduct::query()->create([
            'manufacturer' => 'Masterblend',
            'name' => 'Tomato 4-18-38',
            'component' => 'npk',
        ]);
        $calcium = NutrientProduct::query()->create([
            'manufacturer' => 'Yara',
            'name' => 'YaraLiva Calcinit',
            'component' => 'calcium',
        ]);
        $magnesium = NutrientProduct::query()->create([
            'manufacturer' => 'TerraTarsa',
            'name' => 'MgSO4',
            'component' => 'magnesium',
        ]);
        $micro = NutrientProduct::query()->create([
            'manufacturer' => 'Haifa',
            'name' => 'Micro Hydroponic Mix',
            'component' => 'micro',
        ]);

        $zone = Zone::factory()->create();
        $recipe = Recipe::factory()->create();
        $revision = RecipeRevision::factory()->create([
            'recipe_id' => $recipe->id,
            'status' => 'PUBLISHED',
        ]);

        $phase = RecipeRevisionPhase::factory()->create([
            'recipe_revision_id' => $revision->id,
            'phase_index' => 0,
            'name' => 'Nutrition Phase',
            'ec_target' => 2.1,
            'nutrient_program_code' => 'YARAREGA_4PART_V1',
            'nutrient_npk_ratio_pct' => 44,
            'nutrient_calcium_ratio_pct' => 36,
            'nutrient_magnesium_ratio_pct' => 17,
            'nutrient_micro_ratio_pct' => 3,
            'nutrient_npk_dose_ml_l' => 1.8,
            'nutrient_calcium_dose_ml_l' => 1.2,
            'nutrient_magnesium_dose_ml_l' => 0.5,
            'nutrient_micro_dose_ml_l' => 0.2,
            'nutrient_npk_product_id' => $npk->id,
            'nutrient_calcium_product_id' => $calcium->id,
            'nutrient_magnesium_product_id' => $magnesium->id,
            'nutrient_micro_product_id' => $micro->id,
            'nutrient_dose_delay_sec' => 12,
            'nutrient_ec_stop_tolerance' => 0.07,
        ]);

        $cycle = GrowCycle::factory()->create([
            'zone_id' => $zone->id,
            'recipe_revision_id' => $revision->id,
            'status' => GrowCycleStatus::RUNNING,
        ]);

        $snapshotPhase = GrowCyclePhase::factory()->create([
            'grow_cycle_id' => $cycle->id,
            'recipe_revision_phase_id' => $phase->id,
            'phase_index' => 0,
            'name' => 'Nutrition Phase',
            'ec_target' => 2.1,
            'nutrient_program_code' => 'YARAREGA_4PART_V1',
            'nutrient_npk_ratio_pct' => 44,
            'nutrient_calcium_ratio_pct' => 36,
            'nutrient_magnesium_ratio_pct' => 17,
            'nutrient_micro_ratio_pct' => 3,
            'nutrient_npk_dose_ml_l' => 1.8,
            'nutrient_calcium_dose_ml_l' => 1.2,
            'nutrient_magnesium_dose_ml_l' => 0.5,
            'nutrient_micro_dose_ml_l' => 0.2,
            'nutrient_npk_product_id' => $npk->id,
            'nutrient_calcium_product_id' => $calcium->id,
            'nutrient_magnesium_product_id' => $magnesium->id,
            'nutrient_micro_product_id' => $micro->id,
        ]);

        $cycle->update(['current_phase_id' => $snapshotPhase->id]);

        $result = $this->service->getEffectiveTargets($cycle->id);

        $this->assertArrayHasKey('nutrition', $result['targets']);
        $this->assertEquals('YARAREGA_4PART_V1', $result['targets']['nutrition']['program_code']);
        $this->assertEquals(44.0, $result['targets']['nutrition']['components']['npk']['ratio_pct']);
        $this->assertEquals(36.0, $result['targets']['nutrition']['components']['calcium']['ratio_pct']);
        $this->assertEquals(17.0, $result['targets']['nutrition']['components']['magnesium']['ratio_pct']);
        $this->assertEquals(3.0, $result['targets']['nutrition']['components']['micro']['ratio_pct']);
        $this->assertEquals($npk->id, $result['targets']['nutrition']['components']['npk']['product_id']);
        $this->assertEquals('Masterblend', $result['targets']['nutrition']['components']['npk']['manufacturer']);
        $this->assertEquals($calcium->id, $result['targets']['nutrition']['components']['calcium']['product_id']);
        $this->assertEquals('YaraLiva Calcinit', $result['targets']['nutrition']['components']['calcium']['product_name']);
        $this->assertEquals($magnesium->id, $result['targets']['nutrition']['components']['magnesium']['product_id']);
        $this->assertEquals('TerraTarsa', $result['targets']['nutrition']['components']['magnesium']['manufacturer']);
        $this->assertEquals($micro->id, $result['targets']['nutrition']['components']['micro']['product_id']);
        $this->assertEquals('Haifa', $result['targets']['nutrition']['components']['micro']['manufacturer']);
        $this->assertEquals(12, $result['targets']['nutrition']['dose_delay_sec']);
        $this->assertEquals(0.07, $result['targets']['nutrition']['ec_stop_tolerance']);
    }
}
