<?php

namespace Database\Factories;

use App\Models\GrowCycle;
use App\Models\User;
use Illuminate\Database\Eloquent\Factories\Factory;

/**
 * @extends \Illuminate\Database\Eloquent\Factories\Factory<\App\Models\GrowCycleOverride>
 */
class GrowCycleOverrideFactory extends Factory
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
            'parameter' => $this->faker->randomElement(['ph_target', 'ec_target', 'temp_air_target']),
            'value_type' => 'decimal',
            'value' => (string) $this->faker->randomFloat(2, 5.0, 7.0),
            'reason' => $this->faker->sentence(),
            'created_by' => User::factory(),
            'applies_from' => now(),
            'applies_until' => null,
            'is_active' => true,
        ];
    }

    public function active(): static
    {
        return $this->state(fn (array $attributes) => [
            'is_active' => true,
            'applies_from' => now()->subDay(),
            'applies_until' => null,
        ]);
    }

    public function inactive(): static
    {
        return $this->state(fn (array $attributes) => [
            'is_active' => false,
        ]);
    }
}
