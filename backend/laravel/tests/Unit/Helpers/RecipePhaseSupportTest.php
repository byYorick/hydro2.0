<?php

namespace Tests\Unit\Helpers;

use App\Models\NutrientProduct;
use App\Models\RecipeRevisionPhase;
use App\Support\Recipes\RecipePhasePayloadNormalizer;
use App\Support\Recipes\RecipePhasePresenter;
use Tests\TestCase;

class RecipePhaseSupportTest extends TestCase
{
    public function test_normalizer_converts_legacy_day_targets_to_day_night(): void
    {
        $normalizer = new RecipePhasePayloadNormalizer;

        $normalized = $normalizer->normalizeForWrite([
            'extensions' => [
                'day_target' => [
                    'temp_air' => 24.0,
                    'humidity' => 60.0,
                ],
                'night_target' => [
                    'temp_air' => 20.0,
                    'humidity' => 70.0,
                ],
            ],
        ]);

        $this->assertSame(24.0, data_get($normalized, 'extensions.day_night.temperature.day'));
        $this->assertSame(20.0, data_get($normalized, 'extensions.day_night.temperature.night'));
        $this->assertSame(60.0, data_get($normalized, 'extensions.day_night.humidity.day'));
        $this->assertSame(70.0, data_get($normalized, 'extensions.day_night.humidity.night'));
        $this->assertNull(data_get($normalized, 'extensions.day_target'));
        $this->assertNull(data_get($normalized, 'extensions.night_target'));
    }

    public function test_presenter_returns_derived_targets_and_canonical_extensions(): void
    {
        $normalizer = new RecipePhasePayloadNormalizer;
        $presenter = new RecipePhasePresenter($normalizer);

        $phase = new RecipeRevisionPhase([
            'id' => 10,
            'phase_index' => 0,
            'name' => 'VEG',
            'duration_hours' => 72,
            'ph_target' => 5.8,
            'ph_min' => 5.7,
            'ph_max' => 5.9,
            'ec_target' => 1.4,
            'ec_min' => 1.3,
            'ec_max' => 1.5,
            'temp_air_target' => 23.0,
            'humidity_target' => 62.0,
            'lighting_photoperiod_hours' => 16,
            'lighting_start_time' => '2026-03-18 06:00:00',
            'irrigation_mode' => 'SUBSTRATE',
            'irrigation_interval_sec' => 900,
            'irrigation_duration_sec' => 15,
            'extensions' => [
                'day_target' => [
                    'temp_air' => 23.0,
                    'humidity' => 62.0,
                ],
                'night_target' => [
                    'temp_air' => 21.0,
                    'humidity' => 66.0,
                ],
                'subsystems' => [
                    'irrigation' => [
                        'targets' => [
                            'system_type' => 'drip',
                        ],
                    ],
                ],
            ],
        ]);

        $presented = $presenter->present($phase);

        $this->assertSame(23.0, data_get($presented, 'targets.temp_air'));
        $this->assertSame(62.0, data_get($presented, 'targets.humidity_air'));
        $this->assertSame('SUBSTRATE', data_get($presented, 'targets.irrigation.mode'));
        $this->assertSame('drip', data_get($presented, 'targets.irrigation.system_type'));
        $this->assertEquals(23.0, data_get($presented, 'extensions.day_night.temperature.day'));
        $this->assertEquals(21.0, data_get($presented, 'extensions.day_night.temperature.night'));
    }

    public function test_presenter_exposes_mist_solution_and_system_fields(): void
    {
        $presenter = new RecipePhasePresenter(new RecipePhasePayloadNormalizer);

        $phase = new RecipeRevisionPhase([
            'phase_index' => 1,
            'name' => 'GERMINATION',
            'duration_hours' => 96,
            'mist_interval_sec' => 600,
            'mist_duration_sec' => 15,
            'mist_mode' => 'SPRAY',
            'solution_temp_target' => 20.0,
            'solution_temp_min' => 18.0,
            'solution_temp_max' => 22.0,
            'irrigation_system_type' => 'nft',
            'substrate_type' => 'coco',
            'day_night_enabled' => true,
            'nutrient_ec_dosing_mode' => 'parallel',
            'phase_advance_strategy' => 'time',
        ]);

        $presented = $presenter->present($phase);

        $this->assertSame(600, $presented['mist_interval_sec']);
        $this->assertSame(15, $presented['mist_duration_sec']);
        $this->assertSame('SPRAY', $presented['mist_mode']);
        $this->assertSame(20.0, $presented['solution_temp_target']);
        $this->assertSame(18.0, data_get($presented, 'targets.solution_temp.min'));
        $this->assertSame(22.0, data_get($presented, 'targets.solution_temp.max'));
        $this->assertSame('nft', $presented['irrigation_system_type']);
        $this->assertSame('nft', data_get($presented, 'targets.irrigation.system_type'));
        $this->assertSame('coco', $presented['substrate_type']);
        $this->assertTrue($presented['day_night_enabled']);
        $this->assertSame('parallel', $presented['nutrient_ec_dosing_mode']);
        $this->assertSame('time', $presented['phase_advance_strategy']);
    }

    public function test_presenter_includes_loaded_nutrient_products(): void
    {
        $presenter = new RecipePhasePresenter(new RecipePhasePayloadNormalizer);

        $phase = new RecipeRevisionPhase([
            'phase_index' => 0,
            'name' => 'VEG',
            'nutrient_npk_product_id' => 7,
        ]);
        $phase->setRelation('npkProduct', new NutrientProduct([
            'manufacturer' => 'Yara',
            'name' => 'YaraRega',
            'component' => 'npk',
        ]));

        $presented = $presenter->present($phase);

        $this->assertSame('Yara', data_get($presented, 'npk_product.manufacturer'));
        $this->assertSame('YaraRega', data_get($presented, 'npk_product.name'));
        $this->assertNull($presented['calcium_product']);
    }
}
