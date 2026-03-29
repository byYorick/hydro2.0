<?php

namespace Tests\Unit\Helpers;

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
}
