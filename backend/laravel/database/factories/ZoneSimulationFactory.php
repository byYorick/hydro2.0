<?php

namespace Database\Factories;

use App\Models\ZoneSimulation;
use App\Models\Zone;
use App\Models\Recipe;
use Illuminate\Database\Eloquent\Factories\Factory;

/**
 * @extends \Illuminate\Database\Eloquent\Factories\Factory<\App\Models\ZoneSimulation>
 */
class ZoneSimulationFactory extends Factory
{
    protected $model = ZoneSimulation::class;

    public function definition(): array
    {
        return [
            'zone_id' => Zone::factory(),
            'scenario' => [
                'recipe_id' => Recipe::factory(),
                'initial_state' => [
                    'ph' => 6.0,
                    'ec' => 1.2,
                    'temp_air' => 22.0,
                    'temp_water' => 20.0,
                    'humidity_air' => 60.0,
                ],
            ],
            'results' => [
                'points' => [
                    ['t' => 0, 'ph' => 6.0, 'ec' => 1.2, 'temp_air' => 22.0, 'temp_water' => 20.0, 'humidity_air' => 60.0, 'phase_index' => 0],
                ],
                'duration_hours' => 72,
                'step_minutes' => 10,
            ],
            'duration_hours' => 72,
            'step_minutes' => 10,
            'status' => 'completed',
            'error_message' => null,
        ];
    }
}
