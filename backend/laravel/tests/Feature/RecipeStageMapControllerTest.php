<?php

namespace Tests\Feature;

use App\Models\GrowStageTemplate;
use App\Models\Recipe;
use App\Models\RecipeStageMap;
use App\Models\User;
use Illuminate\Foundation\Testing\RefreshDatabase;
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

    /** @test */
    public function it_gets_stage_map_for_recipe()
    {
        $template1 = GrowStageTemplate::factory()->create([
            'code' => 'PLANTING',
            'name' => 'Посадка',
            'order_index' => 0,
        ]);
        $template2 = GrowStageTemplate::factory()->create([
            'code' => 'VEG',
            'name' => 'Вега',
            'order_index' => 1,
        ]);

        RecipeStageMap::factory()->create([
            'recipe_id' => $this->recipe->id,
            'stage_template_id' => $template1->id,
            'order_index' => 0,
        ]);
        RecipeStageMap::factory()->create([
            'recipe_id' => $this->recipe->id,
            'stage_template_id' => $template2->id,
            'order_index' => 1,
        ]);

        $response = $this->actingAs($this->user)
            ->getJson("/api/recipes/{$this->recipe->id}/stage-map");

        $response->assertStatus(200)
            ->assertJsonStructure([
                'status',
                'data' => [
                    '*' => [
                        'id',
                        'stage_template',
                        'order_index',
                        'phase_indices',
                    ],
                ],
            ])
            ->assertJsonCount(2, 'data');
    }

    /** @test */
    public function it_auto_creates_stage_map_if_not_exists()
    {
        $response = $this->actingAs($this->user)
            ->getJson("/api/recipes/{$this->recipe->id}/stage-map");

        $response->assertStatus(200);
        $this->assertTrue($this->recipe->stageMaps()->exists());
    }

    /** @test */
    public function it_updates_stage_map()
    {
        $template1 = GrowStageTemplate::factory()->create(['code' => 'PLANTING', 'order_index' => 0]);
        $template2 = GrowStageTemplate::factory()->create(['code' => 'VEG', 'order_index' => 1]);

        $response = $this->actingAs($this->user)
            ->putJson("/api/recipes/{$this->recipe->id}/stage-map", [
                'stages' => [
                    [
                        'stage_template_id' => $template1->id,
                        'order_index' => 0,
                        'start_offset_days' => 0,
                        'end_offset_days' => 7,
                        'phase_indices' => [0, 1],
                    ],
                    [
                        'stage_template_id' => $template2->id,
                        'order_index' => 1,
                        'start_offset_days' => 7,
                        'end_offset_days' => 30,
                        'phase_indices' => [2, 3],
                    ],
                ],
            ]);

        $response->assertStatus(200)
            ->assertJsonCount(2, 'data');

        $this->assertEquals(2, $this->recipe->stageMaps()->count());
    }

    /** @test */
    public function it_requires_operator_role_to_update()
    {
        $viewer = User::factory()->create(['role' => 'viewer']);

        $response = $this->actingAs($viewer)
            ->putJson("/api/recipes/{$this->recipe->id}/stage-map", [
                'stages' => [],
            ]);

        $response->assertStatus(403);
    }

    /** @test */
    public function it_validates_stage_map_data()
    {
        $response = $this->actingAs($this->user)
            ->putJson("/api/recipes/{$this->recipe->id}/stage-map", [
                'stages' => [
                    [
                        'stage_template_id' => 99999, // Несуществующий ID
                        'order_index' => 0,
                    ],
                ],
            ]);

        $response->assertStatus(422);
    }
}

