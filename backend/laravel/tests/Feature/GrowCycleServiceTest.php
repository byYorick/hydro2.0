<?php

namespace Tests\Feature;

use App\Models\GrowCycle;
use App\Models\GrowStageTemplate;
use App\Models\Recipe;
use App\Models\RecipePhase;
use App\Models\RecipeStageMap;
use App\Models\Zone;
use App\Models\ZoneRecipeInstance;
use App\Enums\GrowCycleStatus;
use App\Services\GrowCycleService;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Tests\TestCase;
use Carbon\Carbon;

class GrowCycleServiceTest extends TestCase
{
    use RefreshDatabase;

    private GrowCycleService $service;

    protected function setUp(): void
    {
        parent::setUp();
        $this->service = app(GrowCycleService::class);
    }

    /** @test */
    public function it_creates_a_grow_cycle()
    {
        $zone = Zone::factory()->create();
        $recipe = Recipe::factory()->create();
        
        $cycle = $this->service->createCycle($zone, $recipe);

        $this->assertDatabaseHas('grow_cycles', [
            'id' => $cycle->id,
            'zone_id' => $zone->id,
            'recipe_id' => $recipe->id,
            'status' => GrowCycleStatus::PLANNED->value,
        ]);
    }

    /** @test */
    public function it_creates_stage_map_when_creating_cycle()
    {
        $zone = Zone::factory()->create();
        $recipe = Recipe::factory()->create();
        
        // Создаем фазы рецепта
        RecipePhase::factory()->count(3)->create([
            'recipe_id' => $recipe->id,
            'phase_index' => 0,
        ]);
        RecipePhase::factory()->create([
            'recipe_id' => $recipe->id,
            'phase_index' => 1,
        ]);
        RecipePhase::factory()->create([
            'recipe_id' => $recipe->id,
            'phase_index' => 2,
        ]);

        $cycle = $this->service->createCycle($zone, $recipe);

        $this->assertTrue($recipe->stageMaps()->exists());
    }

    /** @test */
    public function it_starts_a_cycle()
    {
        $zone = Zone::factory()->create();
        $recipe = Recipe::factory()->create();
        
        $cycle = $this->service->createCycle($zone, $recipe);
        $plantingAt = Carbon::now();

        $startedCycle = $this->service->startCycle($cycle, $plantingAt);

        $this->assertEquals(GrowCycleStatus::RUNNING, $startedCycle->status);
        $this->assertNotNull($startedCycle->planting_at);
        $this->assertNotNull($startedCycle->current_stage_code);
    }

    /** @test */
    public function it_computes_expected_harvest()
    {
        $zone = Zone::factory()->create();
        $recipe = Recipe::factory()->create();
        
        // Создаем стадии с offset
        $template1 = GrowStageTemplate::factory()->create([
            'code' => 'PLANTING',
            'default_duration_days' => 1,
        ]);
        $template2 = GrowStageTemplate::factory()->create([
            'code' => 'VEG',
            'default_duration_days' => 30,
        ]);

        RecipeStageMap::factory()->create([
            'recipe_id' => $recipe->id,
            'stage_template_id' => $template1->id,
            'order_index' => 0,
            'start_offset_days' => 0,
            'end_offset_days' => 1,
        ]);
        RecipeStageMap::factory()->create([
            'recipe_id' => $recipe->id,
            'stage_template_id' => $template2->id,
            'order_index' => 1,
            'start_offset_days' => 1,
            'end_offset_days' => 31,
        ]);

        $cycle = $this->service->createCycle($zone, $recipe);
        $plantingAt = Carbon::now();
        $startedCycle = $this->service->startCycle($cycle, $plantingAt);

        $this->assertNotNull($startedCycle->expected_harvest_at);
        $expectedHarvest = Carbon::parse($startedCycle->expected_harvest_at);
        $this->assertEquals(31, $plantingAt->diffInDays($expectedHarvest));
    }

    /** @test */
    public function it_advances_stage_automatically()
    {
        $zone = Zone::factory()->create();
        $recipe = Recipe::factory()->create();
        
        $template1 = GrowStageTemplate::factory()->create([
            'code' => 'PLANTING',
            'order_index' => 0,
        ]);
        $template2 = GrowStageTemplate::factory()->create([
            'code' => 'VEG',
            'order_index' => 1,
        ]);

        RecipeStageMap::factory()->create([
            'recipe_id' => $recipe->id,
            'stage_template_id' => $template1->id,
            'order_index' => 0,
        ]);
        RecipeStageMap::factory()->create([
            'recipe_id' => $recipe->id,
            'stage_template_id' => $template2->id,
            'order_index' => 1,
        ]);

        $cycle = $this->service->createCycle($zone, $recipe);
        $cycle = $this->service->startCycle($cycle);
        $cycle->update(['current_stage_code' => 'PLANTING']);

        $advancedCycle = $this->service->advanceStage($cycle);

        $this->assertEquals('VEG', $advancedCycle->current_stage_code);
    }

    /** @test */
    public function it_advances_to_specific_stage()
    {
        $zone = Zone::factory()->create();
        $recipe = Recipe::factory()->create();
        
        $template1 = GrowStageTemplate::factory()->create(['code' => 'PLANTING', 'order_index' => 0]);
        $template2 = GrowStageTemplate::factory()->create(['code' => 'VEG', 'order_index' => 1]);
        $template3 = GrowStageTemplate::factory()->create(['code' => 'FLOWER', 'order_index' => 2]);

        RecipeStageMap::factory()->create([
            'recipe_id' => $recipe->id,
            'stage_template_id' => $template1->id,
            'order_index' => 0,
        ]);
        RecipeStageMap::factory()->create([
            'recipe_id' => $recipe->id,
            'stage_template_id' => $template2->id,
            'order_index' => 1,
        ]);
        RecipeStageMap::factory()->create([
            'recipe_id' => $recipe->id,
            'stage_template_id' => $template3->id,
            'order_index' => 2,
        ]);

        $cycle = $this->service->createCycle($zone, $recipe);
        $cycle = $this->service->startCycle($cycle);
        $cycle->update(['current_stage_code' => 'PLANTING']);

        $advancedCycle = $this->service->advanceStage($cycle, 'FLOWER');

        $this->assertEquals('FLOWER', $advancedCycle->current_stage_code);
    }

    /** @test */
    public function it_computes_stage_from_recipe_instance()
    {
        $zone = Zone::factory()->create();
        $recipe = Recipe::factory()->create();
        $instance = ZoneRecipeInstance::factory()->create([
            'zone_id' => $zone->id,
            'recipe_id' => $recipe->id,
        ]);
        $zone->recipeInstance()->associate($instance);

        $template = GrowStageTemplate::factory()->create([
            'code' => 'VEG',
            'order_index' => 0,
        ]);

        RecipeStageMap::factory()->create([
            'recipe_id' => $recipe->id,
            'stage_template_id' => $template->id,
            'order_index' => 0,
            'start_offset_days' => 0,
        ]);

        $cycle = $this->service->createCycle($zone, $recipe);
        $cycle = $this->service->startCycle($cycle);

        $this->service->computeStageFromRecipeInstance($cycle);

        $this->assertNotNull($cycle->fresh()->current_stage_code);
    }

    /** @test */
    public function it_ensures_recipe_stage_map_exists()
    {
        $recipe = Recipe::factory()->create();
        
        RecipePhase::factory()->count(3)->create([
            'recipe_id' => $recipe->id,
            'phase_index' => 0,
        ]);
        RecipePhase::factory()->create([
            'recipe_id' => $recipe->id,
            'phase_index' => 1,
        ]);

        $this->service->ensureRecipeStageMap($recipe);

        $this->assertTrue($recipe->stageMaps()->exists());
    }
}

