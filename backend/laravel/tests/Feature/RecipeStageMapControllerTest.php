<?php

namespace Tests\Feature;

use App\Models\Recipe;
use App\Models\RecipeRevision;
use App\Models\RecipeRevisionPhase;
use App\Models\User;
use Tests\RefreshDatabase;
use PHPUnit\Framework\Attributes\Test;
use Tests\TestCase;

class RecipeStageMapControllerTest extends TestCase
{
    use RefreshDatabase;

    private User $user;

    private Recipe $recipe;

    protected function setUp(): void
    {
        parent::setUp();
        $this->user = User::factory()->create(['role' => 'operator']);
        $this->recipe = Recipe::factory()->create();
    }

    #[Test]
    public function it_gets_stage_map_for_recipe(): void
    {
        $revision = RecipeRevision::factory()->create([
            'recipe_id' => $this->recipe->id,
            'status' => 'PUBLISHED',
        ]);
        RecipeRevisionPhase::factory()->count(2)->create([
            'recipe_revision_id' => $revision->id,
        ]);

        $response = $this->actingAs($this->user)
            ->getJson("/api/recipes/{$this->recipe->id}/stage-map");

        $response->assertStatus(200)
            ->assertJsonStructure([
                'status',
                'data' => [
                    'recipe_id',
                    'stage_map',
                ],
            ]);
    }

    #[Test]
    public function it_auto_generates_stage_map_when_missing(): void
    {
        $revision = RecipeRevision::factory()->create([
            'recipe_id' => $this->recipe->id,
            'status' => 'PUBLISHED',
        ]);
        RecipeRevisionPhase::factory()->create([
            'recipe_revision_id' => $revision->id,
            'phase_index' => 0,
            'name' => 'Посадка',
        ]);

        $response = $this->actingAs($this->user)
            ->getJson("/api/recipes/{$this->recipe->id}/stage-map");

        $response->assertStatus(200)
            ->assertJsonPath('data.recipe_id', $this->recipe->id)
            ->assertJsonStructure([
                'data' => [
                    'stage_map' => [
                        '*' => ['phase_index', 'phase_name', 'stage'],
                    ],
                ],
            ]);
    }

    #[Test]
    public function it_updates_stage_map(): void
    {
        $response = $this->actingAs($this->user)
            ->putJson("/api/recipes/{$this->recipe->id}/stage-map", [
                'stage_map' => [
                    ['phase_index' => 0, 'stage' => 'planting'],
                    ['phase_index' => 1, 'stage' => 'veg'],
                ],
            ]);

        $response->assertStatus(200)
            ->assertJsonStructure([
                'status',
                'data' => [
                    'recipe_id',
                    'stage_map',
                ],
            ])
            ->assertJsonCount(2, 'data.stage_map');
    }

    #[Test]
    public function it_requires_authentication_to_update(): void
    {
        $response = $this->putJson("/api/recipes/{$this->recipe->id}/stage-map", [
            'stage_map' => [],
        ]);

        $response->assertStatus(401);
    }

    #[Test]
    public function it_validates_stage_map_data(): void
    {
        $response = $this->actingAs($this->user)
            ->putJson("/api/recipes/{$this->recipe->id}/stage-map", [
                'stage_map' => [
                    ['phase_index' => 0, 'stage' => 'invalid'],
                ],
            ]);

        $response->assertStatus(422);
    }
}
