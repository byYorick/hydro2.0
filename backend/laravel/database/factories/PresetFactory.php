<?php

namespace Database\Factories;

use App\Models\Preset;
use Illuminate\Database\Eloquent\Factories\Factory;

/**
 * @extends \Illuminate\Database\Eloquent\Factories\Factory<\App\Models\Preset>
 */
class PresetFactory extends Factory
{
    protected $model = Preset::class;

    public function definition(): array
    {
        return [
            'name' => $this->faker->words(2, true).' Preset',
            'plant_type' => $this->faker->randomElement(['lettuce', 'arugula', 'tomato', 'basil', 'strawberry']),
            'ph_optimal_range' => ['min' => 5.5, 'max' => 6.5],
            'ec_range' => ['min' => 1.0, 'max' => 2.0],
            'vpd_range' => ['min' => 0.8, 'max' => 1.2],
            'light_intensity_range' => ['min' => 200, 'max' => 500],
            'climate_ranges' => [
                'temp_day' => ['min' => 20, 'max' => 24],
                'temp_night' => ['min' => 18, 'max' => 20],
                'humidity_day' => ['min' => 55, 'max' => 65],
                'humidity_night' => ['min' => 60, 'max' => 70],
            ],
            'irrigation_behavior' => [
                'interval_sec' => 900,
                'duration_sec' => 8,
                'adaptive' => true,
            ],
            'growth_profile' => $this->faker->randomElement(['fast', 'mid', 'slow']),
            'description' => $this->faker->sentence(),
        ];
    }
}

