<?php

namespace Tests\Feature;

use App\Enums\GrowCycleStatus;
use App\Models\GrowStageTemplate;
use App\Models\Plant;
use App\Models\Recipe;
use App\Models\RecipeRevision;
use App\Models\RecipeRevisionPhase;
use App\Models\Zone;
use App\Services\GrowCycleService;
use Carbon\Carbon;
use Illuminate\Foundation\Testing\RefreshDatabase;
use PHPUnit\Framework\Attributes\Test;
use Tests\TestCase;

class GrowCycleServiceTest extends TestCase
{
    use RefreshDatabase;

    private GrowCycleService $service;

    protected function setUp(): void
    {
        parent::setUp();
        $this->service = app(GrowCycleService::class);
    }

    #[Test]
    public function it_creates_a_grow_cycle(): void
    {
        $zone = Zone::factory()->create();
        $plant = Plant::factory()->create();
        $recipe = Recipe::factory()->create();
        $revision = RecipeRevision::factory()->create([
            'recipe_id' => $recipe->id,
            'status' => 'PUBLISHED',
        ]);
        RecipeRevisionPhase::factory()->create([
            'recipe_revision_id' => $revision->id,
            'phase_index' => 0,
        ]);

        $cycle = $this->service->createCycle($zone, $revision, $plant->id);

        $this->assertDatabaseHas('grow_cycles', [
            'id' => $cycle->id,
            'zone_id' => $zone->id,
            'recipe_revision_id' => $revision->id,
            'plant_id' => $plant->id,
            'status' => GrowCycleStatus::PLANNED->value,
        ]);
        $this->assertNotNull($cycle->current_phase_id);
    }

    #[Test]
    public function it_starts_a_cycle(): void
    {
        $zone = Zone::factory()->create();
        $plant = Plant::factory()->create();
        $recipe = Recipe::factory()->create();
        $revision = RecipeRevision::factory()->create([
            'recipe_id' => $recipe->id,
            'status' => 'PUBLISHED',
        ]);
        RecipeRevisionPhase::factory()->create([
            'recipe_revision_id' => $revision->id,
            'phase_index' => 0,
        ]);

        $cycle = $this->service->createCycle($zone, $revision, $plant->id);
        $plantingAt = Carbon::now();

        $startedCycle = $this->service->startCycle($cycle, $plantingAt);

        $this->assertEquals(GrowCycleStatus::RUNNING, $startedCycle->status);
        $this->assertNotNull($startedCycle->planting_at);
    }

    #[Test]
    public function it_computes_expected_harvest(): void
    {
        $zone = Zone::factory()->create();
        $plant = Plant::factory()->create();
        $recipe = Recipe::factory()->create();
        $revision = RecipeRevision::factory()->create([
            'recipe_id' => $recipe->id,
            'status' => 'PUBLISHED',
        ]);

        RecipeRevisionPhase::factory()->create([
            'recipe_revision_id' => $revision->id,
            'phase_index' => 0,
            'duration_hours' => 24,
        ]);
        RecipeRevisionPhase::factory()->create([
            'recipe_revision_id' => $revision->id,
            'phase_index' => 1,
            'duration_hours' => 24 * 30,
        ]);

        $cycle = $this->service->createCycle($zone, $revision, $plant->id);
        $plantingAt = Carbon::now();
        $startedCycle = $this->service->startCycle($cycle, $plantingAt);

        $this->assertNotNull($startedCycle->expected_harvest_at);
        $expectedHarvest = Carbon::parse($startedCycle->expected_harvest_at);
        $this->assertEquals(31, $plantingAt->diffInDays($expectedHarvest));
    }

    #[Test]
    public function it_advances_stage_automatically(): void
    {
        $zone = Zone::factory()->create();
        $plant = Plant::factory()->create();
        $recipe = Recipe::factory()->create();

        $template1 = GrowStageTemplate::factory()->create([
            'code' => 'PLANTING',
            'order_index' => 0,
        ]);
        $template2 = GrowStageTemplate::factory()->create([
            'code' => 'VEG',
            'order_index' => 1,
        ]);

        $revision = RecipeRevision::factory()->create([
            'recipe_id' => $recipe->id,
            'status' => 'PUBLISHED',
        ]);

        RecipeRevisionPhase::factory()->create([
            'recipe_revision_id' => $revision->id,
            'phase_index' => 0,
            'stage_template_id' => $template1->id,
        ]);
        RecipeRevisionPhase::factory()->create([
            'recipe_revision_id' => $revision->id,
            'phase_index' => 1,
            'stage_template_id' => $template2->id,
        ]);

        $cycle = $this->service->createCycle($zone, $revision, $plant->id);
        $cycle = $this->service->startCycle($cycle);
        $cycle->update(['current_stage_code' => 'PLANTING']);

        $advancedCycle = $this->service->advanceStage($cycle);

        $this->assertEquals('VEG', $advancedCycle->current_stage_code);
    }

    #[Test]
    public function it_advances_to_specific_stage(): void
    {
        $zone = Zone::factory()->create();
        $plant = Plant::factory()->create();
        $recipe = Recipe::factory()->create();

        $template1 = GrowStageTemplate::factory()->create(['code' => 'PLANTING', 'order_index' => 0]);
        $template2 = GrowStageTemplate::factory()->create(['code' => 'VEG', 'order_index' => 1]);
        $template3 = GrowStageTemplate::factory()->create(['code' => 'FLOWER', 'order_index' => 2]);

        $revision = RecipeRevision::factory()->create([
            'recipe_id' => $recipe->id,
            'status' => 'PUBLISHED',
        ]);

        RecipeRevisionPhase::factory()->create([
            'recipe_revision_id' => $revision->id,
            'phase_index' => 0,
            'stage_template_id' => $template1->id,
        ]);
        RecipeRevisionPhase::factory()->create([
            'recipe_revision_id' => $revision->id,
            'phase_index' => 1,
            'stage_template_id' => $template2->id,
        ]);
        RecipeRevisionPhase::factory()->create([
            'recipe_revision_id' => $revision->id,
            'phase_index' => 2,
            'stage_template_id' => $template3->id,
        ]);

        $cycle = $this->service->createCycle($zone, $revision, $plant->id);
        $cycle = $this->service->startCycle($cycle);
        $cycle->update(['current_stage_code' => 'PLANTING']);

        $advancedCycle = $this->service->advanceStage($cycle, 'FLOWER');

        $this->assertEquals('FLOWER', $advancedCycle->current_stage_code);
    }
}
