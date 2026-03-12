<?php

namespace Database\Factories;

use App\Models\Harvest;
use App\Models\Zone;
use App\Models\Recipe;
use Illuminate\Database\Eloquent\Factories\Factory;

/**
 * @extends \Illuminate\Database\Eloquent\Factories\Factory<\App\Models\Harvest>
 */
class HarvestFactory extends Factory
{
    protected $model = Harvest::class;

    public function definition(): array
    {
        return [
            'zone_id' => Zone::factory(),
            'recipe_id' => Recipe::factory(),
            'harvest_date' => $this->faker->dateTimeBetween('-1 month', 'now'),
            'yield_weight_kg' => $this->faker->randomFloat(2, 1, 50),
            'yield_count' => $this->faker->numberBetween(5, 100),
            'quality_score' => $this->faker->randomFloat(2, 5, 10),
            'notes' => ['comment' => $this->faker->sentence()],
        ];
    }
}

