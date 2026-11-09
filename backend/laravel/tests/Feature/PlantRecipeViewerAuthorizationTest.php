<?php

namespace Tests\Feature;

use App\Models\Plant;
use App\Models\Recipe;
use App\Models\User;
use Illuminate\Support\Facades\Gate;
use Tests\RefreshDatabase;
use Tests\TestCase;

class PlantRecipeViewerAuthorizationTest extends TestCase
{
    use RefreshDatabase;

    public function test_viewer_cannot_mutate_plants_or_recipes(): void
    {
        $viewer = User::factory()->create(['role' => 'viewer']);
        $plant = Plant::factory()->create(['name' => 'Салат']);
        $recipe = Recipe::factory()->create(['name' => 'Базовый']);

        $this->assertFalse(Gate::forUser($viewer)->allows('create', Plant::class));
        $this->assertFalse(Gate::forUser($viewer)->allows('update', $plant));
        $this->assertFalse(Gate::forUser($viewer)->allows('delete', $plant));
        $this->assertFalse(Gate::forUser($viewer)->allows('create', Recipe::class));
        $this->assertFalse(Gate::forUser($viewer)->allows('update', $recipe));
        $this->assertFalse(Gate::forUser($viewer)->allows('delete', $recipe));

        $this->actingAs($viewer)->postJson('/api/plants', [
            'name' => 'Чужая культура',
        ])->assertForbidden();

        $this->actingAs($viewer)->putJson("/api/plants/{$plant->id}", [
            'name' => 'Подмена',
        ])->assertForbidden();

        $this->actingAs($viewer)->deleteJson("/api/plants/{$plant->id}")->assertForbidden();

        $this->actingAs($viewer)->postJson('/api/plants/with-recipe', [])->assertForbidden();

        $this->actingAs($viewer)->postJson('/api/recipes', [
            'name' => 'Чужой рецепт',
            'plant_id' => $plant->id,
        ])->assertForbidden();

        $this->actingAs($viewer)->patchJson("/api/recipes/{$recipe->id}", [
            'name' => 'Подмена рецепта',
        ])->assertForbidden();

        $this->actingAs($viewer)->deleteJson("/api/recipes/{$recipe->id}")->assertForbidden();

        $this->actingAs($viewer)->get('/recipes/create')->assertForbidden();
        $this->actingAs($viewer)->get("/recipes/{$recipe->id}/edit")->assertForbidden();

        $this->assertDatabaseHas('plants', ['id' => $plant->id, 'name' => 'Салат']);
        $this->assertDatabaseHas('recipes', ['id' => $recipe->id, 'name' => 'Базовый']);
        $this->assertDatabaseMissing('plants', ['name' => 'Чужая культура']);
    }

    public function test_viewer_can_read_plants_and_recipes(): void
    {
        $viewer = User::factory()->create(['role' => 'viewer']);
        $plant = Plant::factory()->create();
        $recipe = Recipe::factory()->create();

        $this->assertTrue(Gate::forUser($viewer)->allows('view', $plant));
        $this->assertTrue(Gate::forUser($viewer)->allows('view', $recipe));

        $this->actingAs($viewer)->getJson('/api/plants')->assertOk();
        $this->actingAs($viewer)->getJson("/api/plants/{$plant->id}")->assertOk();
        $this->actingAs($viewer)->getJson('/api/recipes')->assertOk();
        $this->actingAs($viewer)->getJson("/api/recipes/{$recipe->id}")->assertOk();
        $this->actingAs($viewer)->get('/recipes')->assertOk();
        $this->actingAs($viewer)->get("/recipes/{$recipe->id}")->assertOk();
    }

    public function test_write_roles_can_create_plant_and_recipe(): void
    {
        foreach (['admin', 'operator', 'agronomist', 'engineer'] as $role) {
            $user = User::factory()->create(['role' => $role]);
            $this->assertTrue(Gate::forUser($user)->allows('create', Plant::class));
            $this->assertTrue(Gate::forUser($user)->allows('create', Recipe::class));

            $this->actingAs($user)->postJson('/api/plants', [
                'name' => "Культура {$role}",
            ])->assertCreated();

            $plant = Plant::query()->where('name', "Культура {$role}")->firstOrFail();

            $this->actingAs($user)->postJson('/api/recipes', [
                'name' => "Рецепт {$role}",
                'plant_id' => $plant->id,
            ])->assertCreated();

            $this->actingAs($user)->get('/recipes/create')->assertOk();
        }
    }
}
