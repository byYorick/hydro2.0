<?php

namespace Tests\Unit\Services;

use App\Models\GrowCycle;
use App\Models\Plant;
use App\Models\Recipe;
use App\Models\RecipeRevision;
use App\Services\RecipeService;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Tests\TestCase;

class RecipeServiceTest extends TestCase
{
    use RefreshDatabase;

    private RecipeService $service;

    protected function setUp(): void
    {
        parent::setUp();
        $this->service = new RecipeService;
    }

    public function test_create_recipe(): void
    {
        $plant = Plant::factory()->create();
        $data = [
            'name' => 'Test Recipe',
            'description' => 'Test Description',
            'plant_id' => $plant->id,
        ];

        $recipe = $this->service->create($data, $plant->id);

        $this->assertInstanceOf(Recipe::class, $recipe);
        $this->assertEquals('Test Recipe', $recipe->name);
        $this->assertDatabaseHas('recipes', [
            'id' => $recipe->id,
            'name' => 'Test Recipe',
        ]);
        $this->assertDatabaseHas('plant_recipe', [
            'plant_id' => $plant->id,
            'recipe_id' => $recipe->id,
        ]);
    }

    public function test_update_recipe(): void
    {
        $recipe = Recipe::factory()->create(['name' => 'Old Name']);
        $newPlant = Plant::factory()->create();

        $updated = $this->service->update($recipe, [
            'name' => 'New Name',
            'plant_id' => $newPlant->id,
        ]);

        $this->assertEquals('New Name', $updated->name);
        $this->assertDatabaseHas('recipes', [
            'id' => $recipe->id,
            'name' => 'New Name',
        ]);
        $this->assertDatabaseHas('plant_recipe', [
            'plant_id' => $newPlant->id,
            'recipe_id' => $recipe->id,
        ]);
    }

    public function test_delete_recipe_without_dependencies(): void
    {
        $recipe = Recipe::factory()->create();

        $this->service->delete($recipe);

        $this->assertDatabaseMissing('recipes', ['id' => $recipe->id]);
    }

    public function test_delete_recipe_used_in_active_grow_cycle_throws_exception(): void
    {
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

        $this->expectException(\DomainException::class);
        $this->expectExceptionMessage('Cannot delete recipe that is used in');

        $this->service->delete($recipe);
    }
}
