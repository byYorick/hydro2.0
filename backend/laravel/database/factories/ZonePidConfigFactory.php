<?php

namespace Database\Factories;

use App\Models\User;
use App\Models\Zone;
use App\Models\ZonePidConfig;
use Illuminate\Database\Eloquent\Factories\Factory;

/**
 * @extends \Illuminate\Database\Eloquent\Factories\Factory<\App\Models\ZonePidConfig>
 */
class ZonePidConfigFactory extends Factory
{
    protected $model = ZonePidConfig::class;

    /**
     * Define the model's default state.
     *
     * @return array<string, mixed>
     */
    public function definition(): array
    {
        return [
            'zone_id' => Zone::factory(),
            'type' => $this->faker->randomElement(['ph', 'ec']),
            'config' => [
                'target' => $this->faker->randomFloat(2, 5.0, 7.0),
                'dead_zone' => 0.2,
                'close_zone' => 0.5,
                'far_zone' => 1.0,
                'zone_coeffs' => [
                    'close' => [
                        'kp' => 10.0,
                        'ki' => 0.0,
                        'kd' => 0.0,
                    ],
                    'far' => [
                        'kp' => 12.0,
                        'ki' => 0.0,
                        'kd' => 0.0,
                    ],
                ],
                'max_output' => 50.0,
                'min_interval_ms' => 60000,
                'enable_autotune' => false,
                'adaptation_rate' => 0.05,
            ],
            'updated_by' => User::factory(),
            'updated_at' => now(),
        ];
    }
}
