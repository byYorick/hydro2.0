<?php

namespace Database\Factories;

use App\Models\Plant;
use App\Models\Recipe;
use Illuminate\Database\Eloquent\Factories\Factory;

/**
 * @extends \Illuminate\Database\Eloquent\Factories\Factory<\App\Models\Recipe>
 */
class RecipeFactory extends Factory
{
    protected $model = Recipe::class;

    public function definition(): array
    {
        return [
            'name' => $this->faker->words(3, true).' Recipe',
            'description' => $this->faker->sentence(),
        ];
    }

    public function configure(): static
    {
        return $this->afterCreating(function (Recipe $recipe) {
            if ($recipe->plants()->count() === 0) {
                $plant = Plant::factory()->create();
                $recipe->plants()->attach($plant->id);
            }
        });
    }
}
