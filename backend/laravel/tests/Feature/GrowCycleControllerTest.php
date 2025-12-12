<?php

namespace Tests\Feature;

use App\Models\GrowCycle;
use App\Models\GrowStageTemplate;
use App\Models\Recipe;
use App\Models\User;
use App\Models\Zone;
use App\Enums\GrowCycleStatus;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Tests\TestCase;

class GrowCycleControllerTest extends TestCase
{
    use RefreshDatabase;

    private User $user;
    private Zone $zone;
    private Recipe $recipe;

    protected function setUp(): void
    {
        parent::setUp();
        $this->user = User::factory()->create(['role' => 'operator']);
        $this->zone = Zone::factory()->create();
        $this->recipe = Recipe::factory()->create();
    }

    /** @test */
    public function it_creates_a_grow_cycle()
    {
        $response = $this->actingAs($this->user)
            ->postJson("/api/zones/{$this->zone->id}/grow-cycles", [
                'recipe_id' => $this->recipe->id,
                'start_immediately' => false,
            ]);

        $response->assertStatus(201)
            ->assertJsonStructure([
                'status',
                'data' => [
                    'id',
                    'zone_id',
                    'recipe_id',
                    'status',
                ],
            ]);

        $this->assertDatabaseHas('grow_cycles', [
            'zone_id' => $this->zone->id,
            'recipe_id' => $this->recipe->id,
            'status' => GrowCycleStatus::PLANNED->value,
        ]);
    }

    /** @test */
    public function it_creates_and_starts_cycle_immediately()
    {
        $response = $this->actingAs($this->user)
            ->postJson("/api/zones/{$this->zone->id}/grow-cycles", [
                'recipe_id' => $this->recipe->id,
                'start_immediately' => true,
            ]);

        $response->assertStatus(201);

        $cycle = GrowCycle::where('zone_id', $this->zone->id)->first();
        $this->assertEquals(GrowCycleStatus::RUNNING, $cycle->status);
        $this->assertNotNull($cycle->planting_at);
    }

    /** @test */
    public function it_gets_active_cycle_with_dto()
    {
        $cycle = GrowCycle::factory()->create([
            'zone_id' => $this->zone->id,
            'recipe_id' => $this->recipe->id,
            'status' => GrowCycleStatus::RUNNING,
            'planting_at' => now(),
        ]);

        $template = GrowStageTemplate::factory()->create([
            'code' => 'VEG',
            'name' => 'Вега',
        ]);

        \App\Models\RecipeStageMap::factory()->create([
            'recipe_id' => $this->recipe->id,
            'stage_template_id' => $template->id,
            'order_index' => 0,
            'start_offset_days' => 0,
        ]);

        $response = $this->actingAs($this->user)
            ->getJson("/api/zones/{$this->zone->id}/grow-cycle");

        $response->assertStatus(200)
            ->assertJsonStructure([
                'status',
                'data' => [
                    'cycle' => [
                        'id',
                        'status',
                        'planting_at',
                        'current_stage',
                        'progress',
                        'stages',
                    ],
                ],
            ]);
    }

    /** @test */
    public function it_advances_stage()
    {
        $cycle = GrowCycle::factory()->create([
            'zone_id' => $this->zone->id,
            'recipe_id' => $this->recipe->id,
            'status' => GrowCycleStatus::RUNNING,
            'current_stage_code' => 'PLANTING',
        ]);

        $template1 = GrowStageTemplate::factory()->create(['code' => 'PLANTING', 'order_index' => 0]);
        $template2 = GrowStageTemplate::factory()->create(['code' => 'VEG', 'order_index' => 1]);

        \App\Models\RecipeStageMap::factory()->create([
            'recipe_id' => $this->recipe->id,
            'stage_template_id' => $template1->id,
            'order_index' => 0,
        ]);
        \App\Models\RecipeStageMap::factory()->create([
            'recipe_id' => $this->recipe->id,
            'stage_template_id' => $template2->id,
            'order_index' => 1,
        ]);

        $response = $this->actingAs($this->user)
            ->postJson("/api/grow-cycles/{$cycle->id}/advance-stage");

        $response->assertStatus(200);

        $cycle->refresh();
        $this->assertEquals('VEG', $cycle->current_stage_code);
    }

    /** @test */
    public function it_pauses_a_cycle()
    {
        $cycle = GrowCycle::factory()->create([
            'zone_id' => $this->zone->id,
            'status' => GrowCycleStatus::RUNNING,
        ]);

        $response = $this->actingAs($this->user)
            ->postJson("/api/zones/{$this->zone->id}/grow-cycle/pause");

        $response->assertStatus(200);

        $cycle->refresh();
        $this->assertEquals(GrowCycleStatus::PAUSED, $cycle->status);
    }

    /** @test */
    public function it_resumes_a_cycle()
    {
        $cycle = GrowCycle::factory()->create([
            'zone_id' => $this->zone->id,
            'status' => GrowCycleStatus::PAUSED,
        ]);

        $response = $this->actingAs($this->user)
            ->postJson("/api/zones/{$this->zone->id}/grow-cycle/resume");

        $response->assertStatus(200);

        $cycle->refresh();
        $this->assertEquals(GrowCycleStatus::RUNNING, $cycle->status);
    }

    /** @test */
    public function it_harvests_a_cycle()
    {
        $cycle = GrowCycle::factory()->create([
            'zone_id' => $this->zone->id,
            'status' => GrowCycleStatus::RUNNING,
        ]);

        $response = $this->actingAs($this->user)
            ->postJson("/api/zones/{$this->zone->id}/grow-cycle/harvest", [
                'batch_label' => 'Batch-001',
            ]);

        $response->assertStatus(200);

        $cycle->refresh();
        $this->assertEquals(GrowCycleStatus::HARVESTED, $cycle->status);
        $this->assertEquals('Batch-001', $cycle->batch_label);
        $this->assertNotNull($cycle->actual_harvest_at);
    }

    /** @test */
    public function it_aborts_a_cycle()
    {
        $cycle = GrowCycle::factory()->create([
            'zone_id' => $this->zone->id,
            'status' => GrowCycleStatus::RUNNING,
        ]);

        $response = $this->actingAs($this->user)
            ->postJson("/api/zones/{$this->zone->id}/grow-cycle/abort", [
                'notes' => 'Emergency stop',
            ]);

        $response->assertStatus(200);

        $cycle->refresh();
        $this->assertEquals(GrowCycleStatus::ABORTED, $cycle->status);
    }

    /** @test */
    public function it_requires_authentication()
    {
        $response = $this->postJson("/api/zones/{$this->zone->id}/grow-cycles");

        $response->assertStatus(401);
    }
}

