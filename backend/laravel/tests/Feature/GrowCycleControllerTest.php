<?php

namespace Tests\Feature;

use App\Enums\GrowCycleStatus;
use App\Models\GrowCycle;
use App\Models\Plant;
use App\Models\Recipe;
use App\Models\RecipeRevision;
use App\Models\RecipeRevisionPhase;
use App\Models\User;
use App\Models\Zone;
use App\Services\GrowCycleService;
use Tests\RefreshDatabase;
use PHPUnit\Framework\Attributes\Test;
use Tests\TestCase;

class GrowCycleControllerTest extends TestCase
{
    use RefreshDatabase;

    private User $user;

    private Zone $zone;

    private Plant $plant;

    private Recipe $recipe;

    private RecipeRevision $revision;

    protected function setUp(): void
    {
        parent::setUp();
        $this->user = User::factory()->create(['role' => 'agronomist']);
        $this->zone = Zone::factory()->create();
        $this->plant = Plant::factory()->create();
        $this->recipe = Recipe::factory()->create();
        $this->revision = RecipeRevision::factory()->create([
            'recipe_id' => $this->recipe->id,
            'status' => 'PUBLISHED',
        ]);
        RecipeRevisionPhase::factory()->create([
            'recipe_revision_id' => $this->revision->id,
            'phase_index' => 0,
        ]);
    }

    #[Test]
    public function it_creates_a_grow_cycle(): void
    {
        $response = $this->actingAs($this->user)
            ->postJson("/api/zones/{$this->zone->id}/grow-cycles", [
                'recipe_revision_id' => $this->revision->id,
                'plant_id' => $this->plant->id,
                'start_immediately' => false,
            ]);

        $response->assertStatus(201)
            ->assertJsonStructure([
                'status',
                'data' => [
                    'id',
                    'zone_id',
                    'recipe_revision_id',
                    'status',
                ],
            ]);

        $this->assertDatabaseHas('grow_cycles', [
            'zone_id' => $this->zone->id,
            'recipe_revision_id' => $this->revision->id,
            'status' => GrowCycleStatus::PLANNED->value,
        ]);
    }

    #[Test]
    public function it_creates_and_starts_cycle_immediately(): void
    {
        $response = $this->actingAs($this->user)
            ->postJson("/api/zones/{$this->zone->id}/grow-cycles", [
                'recipe_revision_id' => $this->revision->id,
                'plant_id' => $this->plant->id,
                'start_immediately' => true,
            ]);

        $response->assertStatus(201);

        $cycle = GrowCycle::where('zone_id', $this->zone->id)->first();
        $this->assertEquals(GrowCycleStatus::RUNNING, $cycle->status);
        $this->assertNotNull($cycle->planting_at);
    }

    #[Test]
    public function it_gets_active_cycle_with_dto(): void
    {
        $service = app(GrowCycleService::class);
        $cycle = $service->createCycle($this->zone, $this->revision, $this->plant->id, ['start_immediately' => true]);

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
                    'effective_targets',
                ],
            ]);
    }

    #[Test]
    public function it_advances_phase(): void
    {
        RecipeRevisionPhase::factory()->create([
            'recipe_revision_id' => $this->revision->id,
            'phase_index' => 1,
        ]);

        $service = app(GrowCycleService::class);
        $cycle = $service->createCycle($this->zone, $this->revision, $this->plant->id, ['start_immediately' => true]);

        $response = $this->actingAs($this->user)
            ->postJson("/api/grow-cycles/{$cycle->id}/advance-phase");

        $response->assertStatus(200);
        $cycle->refresh();
        $this->assertEquals(1, $cycle->currentPhase->phase_index);
    }

    #[Test]
    public function it_pauses_a_cycle(): void
    {
        $cycle = GrowCycle::factory()->create([
            'zone_id' => $this->zone->id,
            'status' => GrowCycleStatus::RUNNING,
        ]);

        $response = $this->actingAs($this->user)
            ->postJson("/api/grow-cycles/{$cycle->id}/pause");

        $response->assertStatus(200);

        $cycle->refresh();
        $this->assertEquals(GrowCycleStatus::PAUSED, $cycle->status);
    }

    #[Test]
    public function it_resumes_a_cycle(): void
    {
        $cycle = GrowCycle::factory()->create([
            'zone_id' => $this->zone->id,
            'status' => GrowCycleStatus::PAUSED,
        ]);

        $response = $this->actingAs($this->user)
            ->postJson("/api/grow-cycles/{$cycle->id}/resume");

        $response->assertStatus(200);

        $cycle->refresh();
        $this->assertEquals(GrowCycleStatus::RUNNING, $cycle->status);
    }

    #[Test]
    public function it_harvests_a_cycle(): void
    {
        $cycle = GrowCycle::factory()->create([
            'zone_id' => $this->zone->id,
            'status' => GrowCycleStatus::RUNNING,
        ]);

        $response = $this->actingAs($this->user)
            ->postJson("/api/grow-cycles/{$cycle->id}/harvest", [
                'batch_label' => 'Batch-001',
            ]);

        $response->assertStatus(200);

        $cycle->refresh();
        $this->assertEquals(GrowCycleStatus::HARVESTED, $cycle->status);
        $this->assertEquals('Batch-001', $cycle->batch_label);
        $this->assertNotNull($cycle->actual_harvest_at);
    }

    #[Test]
    public function it_aborts_a_cycle(): void
    {
        $cycle = GrowCycle::factory()->create([
            'zone_id' => $this->zone->id,
            'status' => GrowCycleStatus::RUNNING,
        ]);

        $response = $this->actingAs($this->user)
            ->postJson("/api/grow-cycles/{$cycle->id}/abort", [
                'notes' => 'Emergency stop',
            ]);

        $response->assertStatus(200);

        $cycle->refresh();
        $this->assertEquals(GrowCycleStatus::ABORTED, $cycle->status);
    }
}
