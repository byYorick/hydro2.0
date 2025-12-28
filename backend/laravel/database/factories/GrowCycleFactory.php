<?php

namespace Database\Factories;

use App\Enums\GrowCycleStatus;
use App\Models\Greenhouse;
use App\Models\GrowCycle;
use App\Models\Plant;
use App\Models\Recipe;
use App\Models\Zone;
use Illuminate\Database\Eloquent\Factories\Factory;

class GrowCycleFactory extends Factory
{
    protected $model = GrowCycle::class;

    public function definition(): array
    {
        $plant = Plant::factory()->create();
        $recipe = Recipe::factory()->create();
        $recipe->plants()->syncWithoutDetaching([$plant->id]);
        $revision = \App\Models\RecipeRevision::factory()->create([
            'recipe_id' => $recipe->id,
            'status' => 'PUBLISHED',
        ]);

        return [
            'greenhouse_id' => Greenhouse::factory(),
            'zone_id' => Zone::factory(),
            'plant_id' => $plant->id,
            'recipe_id' => $recipe->id,
            'recipe_revision_id' => $revision->id,
            'status' => GrowCycleStatus::PLANNED,
            'started_at' => null,
            'recipe_started_at' => null,
            'expected_harvest_at' => null,
            'actual_harvest_at' => null,
            'batch_label' => null,
            'notes' => null,
            'settings' => null,
            'current_phase_id' => null,
            'current_step_id' => null,
            'phase_started_at' => null,
            'step_started_at' => null,
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
            'phase_started_at' => now(),
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
