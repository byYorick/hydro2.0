<?php

namespace Database\Factories;

use App\Models\RecipeAnalytics;
use App\Models\Recipe;
use App\Models\Zone;
use Illuminate\Database\Eloquent\Factories\Factory;

/**
 * @extends \Illuminate\Database\Eloquent\Factories\Factory<\App\Models\RecipeAnalytics>
 */
class RecipeAnalyticsFactory extends Factory
{
    protected $model = RecipeAnalytics::class;

    public function definition(): array
    {
        $startDate = $this->faker->dateTimeBetween('-2 months', '-1 week');
        $endDate = $this->faker->dateTimeBetween($startDate, 'now');

        return [
            'recipe_id' => Recipe::factory(),
            'zone_id' => Zone::factory(),
            'start_date' => $startDate,
            'end_date' => $endDate,
            'total_duration_hours' => $this->faker->numberBetween(100, 1000),
            'avg_ph_deviation' => $this->faker->randomFloat(3, 0, 0.5),
            'avg_ec_deviation' => $this->faker->randomFloat(3, 0, 0.3),
            'alerts_count' => $this->faker->numberBetween(0, 20),
            'final_yield' => [
                'weight_kg' => $this->faker->randomFloat(2, 1, 50),
                'count' => $this->faker->numberBetween(5, 100),
                'quality_score' => $this->faker->randomFloat(2, 5, 10),
            ],
            'efficiency_score' => $this->faker->randomFloat(2, 60, 100),
        ];
    }
}

