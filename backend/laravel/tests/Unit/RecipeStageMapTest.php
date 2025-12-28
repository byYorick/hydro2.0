<?php

namespace Tests\Unit;

use App\Models\GrowStageTemplate;
use App\Models\RecipeRevision;
use App\Models\RecipeRevisionPhase;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Tests\TestCase;

class RecipeRevisionPhaseTest extends TestCase
{
    use RefreshDatabase;

    /** @test */
    public function it_belongs_to_revision()
    {
        $revision = RecipeRevision::factory()->create();
        $phase = RecipeRevisionPhase::factory()->create([
            'recipe_revision_id' => $revision->id,
        ]);

        $this->assertEquals($revision->id, $phase->recipeRevision->id);
    }

    /** @test */
    public function it_belongs_to_stage_template()
    {
        $template = GrowStageTemplate::factory()->create();
        $phase = RecipeRevisionPhase::factory()->create([
            'stage_template_id' => $template->id,
        ]);

        $this->assertEquals($template->id, $phase->stageTemplate->id);
    }

    /** @test */
    public function it_casts_extensions_to_array()
    {
        $phase = RecipeRevisionPhase::factory()->create([
            'extensions' => ['notes' => 'extra'],
        ]);

        $this->assertIsArray($phase->extensions);
        $this->assertEquals('extra', $phase->extensions['notes']);
    }

    /** @test */
    public function it_appends_targets_attribute()
    {
        $phase = RecipeRevisionPhase::factory()->create([
            'ph_min' => 5.5,
            'ph_max' => 6.5,
        ]);

        $this->assertIsArray($phase->targets);
        $this->assertEquals(5.5, $phase->targets['ph']['min']);
    }
}
