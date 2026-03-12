<?php

namespace Database\Factories;

use App\Models\RecipePhase;
use App\Models\Recipe;
use Illuminate\Database\Eloquent\Factories\Factory;

/**
 * @extends \Illuminate\Database\Eloquent\Factories\Factory<\App\Models\RecipePhase>
 */
class RecipePhaseFactory extends Factory
{
    protected $model = RecipePhase::class;

    public function definition(): array
    {
        return [
            'recipe_id' => Recipe::factory(),
            'phase_index' => $this->faker->numberBetween(0, 10),
            'name' => 'Phase '.$this->faker->numberBetween(1, 10),
            'duration_hours' => $this->faker->numberBetween(24, 168),
            'targets' => [
                'ph' => 6.0,
                'ec' => 1.2,
                'temp_air' => 22.0,
                'humidity_air' => 60.0,
            ],
        ];
    }
}

