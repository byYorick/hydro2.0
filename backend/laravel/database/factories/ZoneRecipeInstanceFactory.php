<?php

namespace Database\Factories;

use App\Models\ZoneRecipeInstance;
use App\Models\Zone;
use App\Models\Recipe;
use Illuminate\Database\Eloquent\Factories\Factory;

/**
 * @extends \Illuminate\Database\Eloquent\Factories\Factory<\App\Models\ZoneRecipeInstance>
 */
class ZoneRecipeInstanceFactory extends Factory
{
    protected $model = ZoneRecipeInstance::class;

    public function definition(): array
    {
        return [
            'zone_id' => Zone::factory(),
            'recipe_id' => Recipe::factory(),
            'current_phase_index' => 0,
            'started_at' => now(),
        ];
    }
}

