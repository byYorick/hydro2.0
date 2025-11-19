<?php

namespace Database\Factories;

use App\Models\Alert;
use App\Models\Zone;
use Illuminate\Database\Eloquent\Factories\Factory;

/**
 * @extends \Illuminate\Database\Eloquent\Factories\Factory<\App\Models\Alert>
 */
class AlertFactory extends Factory
{
    protected $model = Alert::class;

    public function definition(): array
    {
        return [
            'zone_id' => Zone::factory(),
            'source' => $this->faker->randomElement(['BIZ', 'AUTOMATION', 'SYSTEM']),
            'code' => $this->faker->randomElement(['BIZ_PH_OUT_OF_RANGE', 'BIZ_EC_OUT_OF_RANGE', 'AUTOMATION_ERROR', 'SYSTEM_ERROR']),
            'type' => $this->faker->randomElement(['ph_high', 'ph_low', 'ec_high', 'ec_low', 'temp_high', 'temp_low', 'node_offline', 'config_error']),
            'status' => $this->faker->randomElement(['active', 'resolved']),
            'details' => [
                'message' => $this->faker->sentence(),
            ],
            'created_at' => now(),
            'resolved_at' => null,
        ];
    }

    public function resolved(): static
    {
        return $this->state(fn (array $attributes) => [
            'status' => 'resolved',
            'resolved_at' => now(),
        ]);
    }
}

