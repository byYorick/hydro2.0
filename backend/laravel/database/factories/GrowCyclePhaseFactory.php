<?php

namespace Database\Factories;

use App\Models\GrowCycle;
use App\Models\RecipeRevisionPhase;
use Illuminate\Database\Eloquent\Factories\Factory;

/**
 * @extends \Illuminate\Database\Eloquent\Factories\Factory<\App\Models\GrowCyclePhase>
 */
class GrowCyclePhaseFactory extends Factory
{
    /**
     * Define the model's default state.
     *
     * @return array<string, mixed>
     */
    public function definition(): array
    {
        return [
            'grow_cycle_id' => GrowCycle::factory(),
            'recipe_revision_phase_id' => RecipeRevisionPhase::factory(),
            'phase_index' => $this->faker->numberBetween(0, 10),
            'name' => 'Phase ' . $this->faker->numberBetween(1, 10),
            'ph_target' => $this->faker->randomFloat(2, 5.5, 6.5),
            'ph_min' => $this->faker->randomFloat(2, 5.0, 6.0),
            'ph_max' => $this->faker->randomFloat(2, 6.0, 7.0),
            'ec_target' => $this->faker->randomFloat(2, 1.0, 2.0),
            'ec_min' => $this->faker->randomFloat(2, 0.8, 1.5),
            'ec_max' => $this->faker->randomFloat(2, 1.5, 2.5),
            'irrigation_mode' => $this->faker->randomElement(['SUBSTRATE', 'RECIRC']),
            'irrigation_interval_sec' => $this->faker->numberBetween(1800, 7200),
            'irrigation_duration_sec' => $this->faker->numberBetween(60, 600),
            'lighting_photoperiod_hours' => $this->faker->numberBetween(12, 18),
            'mist_interval_sec' => $this->faker->numberBetween(3600, 14400),
            'mist_duration_sec' => $this->faker->numberBetween(30, 300),
            'mist_mode' => $this->faker->randomElement(['NORMAL', 'SPRAY']),
            'temp_air_target' => $this->faker->randomFloat(1, 20, 28),
            'humidity_target' => $this->faker->randomFloat(1, 50, 80),
            'duration_hours' => $this->faker->numberBetween(24, 168),
            'progress_model' => 'TIME',
            'started_at' => now(),
            'ended_at' => null,
        ];
    }
}
