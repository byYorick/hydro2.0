<?php

namespace Tests\Unit;

use App\Models\GrowStageTemplate;
use App\Models\Recipe;
use App\Models\RecipeStageMap;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Tests\TestCase;

class RecipeStageMapTest extends TestCase
{
    use RefreshDatabase;

    /** @test */
    public function it_belongs_to_recipe()
    {
        $recipe = Recipe::factory()->create();
        $map = RecipeStageMap::factory()->create([
            'recipe_id' => $recipe->id,
        ]);

        $this->assertEquals($recipe->id, $map->recipe->id);
    }

    /** @test */
    public function it_belongs_to_stage_template()
    {
        $template = GrowStageTemplate::factory()->create();
        $map = RecipeStageMap::factory()->create([
            'stage_template_id' => $template->id,
        ]);

        $this->assertEquals($template->id, $map->stageTemplate->id);
    }

    /** @test */
    public function it_casts_phase_indices_to_array()
    {
        $map = RecipeStageMap::factory()->create([
            'phase_indices' => [0, 1, 2],
        ]);

        $this->assertIsArray($map->phase_indices);
        $this->assertEquals([0, 1, 2], $map->phase_indices);
    }

    /** @test */
    public function it_casts_targets_override_to_array()
    {
        $map = RecipeStageMap::factory()->create([
            'targets_override' => ['ph' => ['min' => 5.5, 'max' => 6.5]],
        ]);

        $this->assertIsArray($map->targets_override);
        $this->assertEquals(5.5, $map->targets_override['ph']['min']);
    }
}

