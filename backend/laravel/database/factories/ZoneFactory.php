<?php

namespace Database\Factories;

use App\Models\Zone;
use App\Models\Greenhouse;
use Illuminate\Database\Eloquent\Factories\Factory;

/**
 * @extends \Illuminate\Database\Eloquent\Factories\Factory<\App\Models\Zone>
 */
class ZoneFactory extends Factory
{
    protected $model = Zone::class;

    public function definition(): array
    {
        return [
            'name' => $this->faker->word(),
            'description' => $this->faker->sentence(),
            'status' => $this->faker->randomElement(['RUNNING', 'PAUSED', 'WARNING', 'ALARM']),
            'greenhouse_id' => Greenhouse::factory(),
        ];
    }
}

