<?php

namespace Database\Factories;

use App\Models\GrowCycle;
use App\Models\Greenhouse;
use App\Models\Zone;
use App\Models\Recipe;
use App\Models\Plant;
use App\Enums\GrowCycleStatus;
use Illuminate\Database\Eloquent\Factories\Factory;

class GrowCycleFactory extends Factory
{
    protected $model = GrowCycle::class;

    public function definition(): array
    {
        return [
            'greenhouse_id' => Greenhouse::factory(),
            'zone_id' => Zone::factory(),
            'plant_id' => null,
            'recipe_id' => Recipe::factory(),
            'zone_recipe_instance_id' => null,
            'status' => GrowCycleStatus::PLANNED,
            'started_at' => null,
            'recipe_started_at' => null,
            'expected_harvest_at' => null,
            'actual_harvest_at' => null,
            'batch_label' => null,
            'notes' => null,
            'settings' => null,
            'current_stage_code' => null,
            'current_stage_started_at' => null,
            'planting_at' => null,
        ];
    }

    public function running(): static
    {
        return $this->state(fn (array $attributes) => [
            'status' => GrowCycleStatus::RUNNING,
            'planting_at' => now(),
            'started_at' => now(),
            'recipe_started_at' => now(),
            'current_stage_code' => 'VEG',
            'current_stage_started_at' => now(),
        ]);
    }

    public function paused(): static
    {
        return $this->state(fn (array $attributes) => [
            'status' => GrowCycleStatus::PAUSED,
            'planting_at' => now()->subDays(10),
            'started_at' => now()->subDays(10),
        ]);
    }

    public function harvested(): static
    {
        return $this->state(fn (array $attributes) => [
            'status' => GrowCycleStatus::HARVESTED,
            'planting_at' => now()->subDays(60),
            'actual_harvest_at' => now()->subDays(1),
        ]);
    }
}

