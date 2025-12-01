<?php

namespace Database\Factories;

use Illuminate\Database\Eloquent\Factories\Factory;
use Illuminate\Support\Str;

/**
 * @extends \Illuminate\Database\Eloquent\Factories\Factory<\App\Models\Plant>
 */
class PlantFactory extends Factory
{
    protected $model = \App\Models\Plant::class;
    /**
     * Define the model's default state.
     *
     * @return array<string, mixed>
     */
    public function definition(): array
    {
        $name = fake()->unique()->words(2, true).' plant';

        return [
            'slug' => Str::slug($name).'-'.Str::random(4),
            'name' => ucfirst($name),
            'species' => fake()->words(2, true),
            'variety' => fake()->word(),
            'substrate_type' => fake()->randomElement(['coco', 'rockwool', 'perlite']),
            'growing_system' => fake()->randomElement(['nft', 'drip', 'ebb_flow']),
            'photoperiod_preset' => fake()->randomElement(['16_8', '18_6', '12_12']),
            'seasonality' => fake()->randomElement(['all_year', 'seasonal', 'multi_cycle']),
            'description' => fake()->sentence(12),
            'environment_requirements' => [
                'temperature' => ['min' => fake()->numberBetween(18, 20), 'max' => fake()->numberBetween(24, 28)],
                'humidity' => ['min' => fake()->numberBetween(55, 60), 'max' => fake()->numberBetween(70, 80)],
            ],
            'growth_phases' => [
                ['name' => 'Вегетация', 'duration_days' => 21],
                ['name' => 'Цветение', 'duration_days' => 28],
            ],
        ];
    }
}
