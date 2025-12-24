<?php

namespace Database\Factories;

use App\Models\RecipeStageMap;
use App\Models\Recipe;
use App\Models\GrowStageTemplate;
use Illuminate\Database\Eloquent\Factories\Factory;

class RecipeStageMapFactory extends Factory
{
    protected $model = RecipeStageMap::class;

    public function definition(): array
    {
        return [
            'recipe_id' => Recipe::factory(),
            'stage_template_id' => GrowStageTemplate::factory(),
            'order_index' => 0,
            'start_offset_days' => null,
            'end_offset_days' => null,
            'phase_indices' => [0],
            'targets_override' => null,
        ];
    }
}

