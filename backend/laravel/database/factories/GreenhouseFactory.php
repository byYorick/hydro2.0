<?php

namespace Database\Factories;

use App\Models\Greenhouse;
use Illuminate\Database\Eloquent\Factories\Factory;

/**
 * @extends \Illuminate\Database\Eloquent\Factories\Factory<\App\Models\Greenhouse>
 */
class GreenhouseFactory extends Factory
{
    protected $model = Greenhouse::class;

    public function definition(): array
    {
        return [
            'uid' => 'gh-'.$this->faker->unique()->numerify('####'),
            'name' => $this->faker->company().' Greenhouse',
            'timezone' => 'Europe/Moscow',
            'type' => $this->faker->randomElement(['indoor', 'outdoor', 'greenhouse']),
            'coordinates' => [
                'lat' => $this->faker->latitude(),
                'lng' => $this->faker->longitude(),
            ],
            'description' => $this->faker->sentence(),
        ];
    }
}

