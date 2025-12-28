<?php

namespace Tests\Feature;

use App\Models\Recipe;
use App\Models\RecipeRevision;
use App\Models\RecipeRevisionPhase;
use App\Models\User;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Inertia\Testing\AssertableInertia;
use Tests\TestCase;

class AdminRecipesTest extends TestCase
{
    use RefreshDatabase;

    public function test_admin_recipes_page_uses_revision_phases_count(): void
    {
        $user = User::factory()->create(['role' => 'admin']);
        $recipe = Recipe::factory()->create();
        $revision = RecipeRevision::factory()->create([
            'recipe_id' => $recipe->id,
            'revision_number' => 1,
            'status' => 'PUBLISHED',
        ]);

        RecipeRevisionPhase::factory()->count(2)->create([
            'recipe_revision_id' => $revision->id,
        ]);

        $response = $this->actingAs($user)->get('/admin/recipes');

        $response->assertStatus(200)
            ->assertInertia(function (AssertableInertia $page) use ($recipe) {
                $page->component('Admin/Recipes')
                    ->where('recipes.0.id', $recipe->id)
                    ->where('recipes.0.phases_count', 2);
            });
    }
}
