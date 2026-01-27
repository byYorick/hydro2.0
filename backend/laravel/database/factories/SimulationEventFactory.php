<?php

namespace Database\Factories;

use App\Models\SimulationEvent;
use App\Models\ZoneSimulation;
use Illuminate\Database\Eloquent\Factories\Factory;

/**
 * @extends \Illuminate\Database\Eloquent\Factories\Factory<\App\Models\SimulationEvent>
 */
class SimulationEventFactory extends Factory
{
    protected $model = SimulationEvent::class;

    public function definition(): array
    {
        $simulation = ZoneSimulation::factory()->create();

        return [
            'simulation_id' => $simulation->id,
            'zone_id' => $simulation->zone_id,
            'service' => $this->faker->randomElement(['laravel', 'digital-twin', 'node-sim-manager']),
            'stage' => $this->faker->randomElement(['job', 'live_init', 'session_start', 'live_complete']),
            'status' => $this->faker->randomElement(['running', 'completed', 'failed', 'requested']),
            'level' => $this->faker->randomElement(['info', 'warning', 'error']),
            'message' => $this->faker->sentence(),
            'payload' => [
                'job_id' => $this->faker->uuid,
            ],
            'occurred_at' => now()->subMinutes($this->faker->numberBetween(0, 120)),
            'created_at' => now(),
        ];
    }
}
