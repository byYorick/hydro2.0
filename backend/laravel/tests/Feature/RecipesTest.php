<?php

namespace Tests\Feature;

use App\Models\GrowCycle;
use App\Models\Plant;
use App\Models\Recipe;
use App\Models\RecipeRevision;
use App\Models\RecipeRevisionPhase;
use App\Models\User;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Tests\TestCase;

class RecipesTest extends TestCase
{
    use RefreshDatabase;

    private function token(string $role = 'operator'): string
    {
        $user = User::factory()->create(['role' => $role]);
        $this->actingAs($user);

        return $user->createToken('test')->plainTextToken;
    }

    public function test_recipes_requires_auth(): void
    {
        $this->getJson('/api/recipes')->assertStatus(401);
    }

    public function test_create_recipe(): void
    {
        $token = $this->token();
        $plant = Plant::factory()->create();
        $resp = $this->withHeader('Authorization', 'Bearer '.$token)->postJson('/api/recipes', [
            'name' => 'Test Recipe',
            'description' => 'Test Description',
            'plant_id' => $plant->id,
        ]);
        $resp->assertCreated()->assertJsonPath('data.name', 'Test Recipe');
    }

    public function test_get_recipes_list(): void
    {
        $token = $this->token();
        Recipe::factory()->count(3)->create();

        $resp = $this->withHeader('Authorization', 'Bearer '.$token)
            ->getJson('/api/recipes');

        $resp->assertOk()
            ->assertJsonStructure(['status', 'data' => ['data', 'current_page']]);
    }

    public function test_get_recipe_details(): void
    {
        $token = $this->token();
        $recipe = Recipe::factory()->create();
        $revision = RecipeRevision::factory()->create([
            'recipe_id' => $recipe->id,
            'status' => 'PUBLISHED',
        ]);
        RecipeRevisionPhase::factory()->count(2)->create([
            'recipe_revision_id' => $revision->id,
        ]);

        $resp = $this->withHeader('Authorization', 'Bearer '.$token)
            ->getJson("/api/recipes/{$recipe->id}");

        $resp->assertOk()
            ->assertJsonPath('data.id', $recipe->id)
            ->assertJsonPath('data.name', $recipe->name)
            ->assertJsonCount(2, 'data.phases');
    }

    public function test_update_recipe(): void
    {
        $token = $this->token();
        $recipe = Recipe::factory()->create(['name' => 'Old Name']);

        $resp = $this->withHeader('Authorization', 'Bearer '.$token)
            ->patchJson("/api/recipes/{$recipe->id}", ['name' => 'New Name']);

        $resp->assertOk()
            ->assertJsonPath('data.name', 'New Name');
    }

    public function test_delete_recipe_without_dependencies(): void
    {
        $token = $this->token();
        $recipe = Recipe::factory()->create();

        $resp = $this->withHeader('Authorization', 'Bearer '.$token)
            ->deleteJson("/api/recipes/{$recipe->id}");

        $resp->assertOk();
        $this->assertDatabaseMissing('recipes', ['id' => $recipe->id]);
    }

    public function test_delete_recipe_used_in_zones_returns_error(): void
    {
        $token = $this->token();
        $recipe = Recipe::factory()->create();
        $revision = RecipeRevision::factory()->create([
            'recipe_id' => $recipe->id,
            'status' => 'PUBLISHED',
        ]);
        GrowCycle::factory()->create([
            'recipe_revision_id' => $revision->id,
            'recipe_id' => $recipe->id,
            'status' => \App\Enums\GrowCycleStatus::PLANNED,
        ]);

        $resp = $this->withHeader('Authorization', 'Bearer '.$token)
            ->deleteJson("/api/recipes/{$recipe->id}");

        $resp->assertStatus(422)
            ->assertJsonPath('status', 'error')
            ->assertJsonPath('message', 'Cannot delete recipe that is used in 1 active grow cycle(s). Please finish or abort cycles first.');
    }

    public function test_add_phase_to_recipe(): void
    {
        $token = $this->token();
        $recipe = Recipe::factory()->create();
        $revision = RecipeRevision::factory()->create([
            'recipe_id' => $recipe->id,
            'status' => 'DRAFT',
        ]);

        $resp = $this->withHeader('Authorization', 'Bearer '.$token)
            ->postJson("/api/recipe-revisions/{$revision->id}/phases", [
                'phase_index' => 0,
                'name' => 'Phase 1',
                'duration_hours' => 24,
                'ph_min' => 5.6,
                'ph_max' => 6.0,
            ]);

        $resp->assertCreated()
            ->assertJsonPath('data.name', 'Phase 1');
        $this->assertDatabaseHas('recipe_revision_phases', [
            'recipe_revision_id' => $revision->id,
            'name' => 'Phase 1',
        ]);
    }

    public function test_update_phase(): void
    {
        $token = $this->token();
        $phase = RecipeRevisionPhase::factory()->create(['name' => 'Old Phase']);

        $resp = $this->withHeader('Authorization', 'Bearer '.$token)
            ->patchJson("/api/recipe-revision-phases/{$phase->id}", [
                'name' => 'New Phase',
            ]);

        $resp->assertOk()
            ->assertJsonPath('data.name', 'New Phase');
    }

    public function test_delete_phase(): void
    {
        $token = $this->token();
        $phase = RecipeRevisionPhase::factory()->create();

        $resp = $this->withHeader('Authorization', 'Bearer '.$token)
            ->deleteJson("/api/recipe-revision-phases/{$phase->id}");

        $resp->assertOk();
        $this->assertDatabaseMissing('recipe_revision_phases', ['id' => $phase->id]);
    }
}
