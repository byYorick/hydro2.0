<?php

namespace Tests\Unit\Services;

use App\Models\Recipe;
use App\Models\Zone;
use App\Models\RecipePhase;
use App\Models\ZoneRecipeInstance;
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
        $this->service = new RecipeService();
    }

    public function test_create_recipe(): void
    {
        $data = [
            'name' => 'Test Recipe',
            'description' => 'Test Description',
        ];

        $recipe = $this->service->create($data);

        $this->assertInstanceOf(Recipe::class, $recipe);
        $this->assertEquals('Test Recipe', $recipe->name);
        $this->assertDatabaseHas('recipes', [
            'id' => $recipe->id,
            'name' => 'Test Recipe',
        ]);
    }

    public function test_update_recipe(): void
    {
        $recipe = Recipe::factory()->create(['name' => 'Old Name']);

        $updated = $this->service->update($recipe, ['name' => 'New Name']);

        $this->assertEquals('New Name', $updated->name);
        $this->assertDatabaseHas('recipes', [
            'id' => $recipe->id,
            'name' => 'New Name',
        ]);
    }

    public function test_delete_recipe_without_dependencies(): void
    {
        $recipe = Recipe::factory()->create();

        $this->service->delete($recipe);

        $this->assertDatabaseMissing('recipes', ['id' => $recipe->id]);
    }

    public function test_delete_recipe_used_in_zones_throws_exception(): void
    {
        $recipe = Recipe::factory()->create();
        ZoneRecipeInstance::factory()->create(['recipe_id' => $recipe->id]);

        $this->expectException(\DomainException::class);
        $this->expectExceptionMessage('Cannot delete recipe that is used');

        $this->service->delete($recipe);
    }

    public function test_add_phase_to_recipe(): void
    {
        $recipe = Recipe::factory()->create();
        $phaseData = [
            'phase_index' => 0,
            'name' => 'Phase 1',
            'duration_hours' => 24,
            'targets' => ['ph' => ['min' => 5.6, 'max' => 6.0]],
        ];

        $phase = $this->service->addPhase($recipe, $phaseData);

        $this->assertInstanceOf(RecipePhase::class, $phase);
        $this->assertEquals($recipe->id, $phase->recipe_id);
        $this->assertEquals('Phase 1', $phase->name);
        $this->assertDatabaseHas('recipe_phases', [
            'recipe_id' => $recipe->id,
            'name' => 'Phase 1',
        ]);
    }

    public function test_update_phase(): void
    {
        $recipe = Recipe::factory()->create();
        $phase = RecipePhase::factory()->create([
            'recipe_id' => $recipe->id,
            'name' => 'Old Phase',
        ]);

        $updated = $this->service->updatePhase($phase, ['name' => 'New Phase']);

        $this->assertEquals('New Phase', $updated->name);
        $this->assertDatabaseHas('recipe_phases', [
            'id' => $phase->id,
            'name' => 'New Phase',
        ]);
    }

    public function test_delete_phase(): void
    {
        $recipe = Recipe::factory()->create();
        $phase = RecipePhase::factory()->create(['recipe_id' => $recipe->id]);

        $this->service->deletePhase($phase);

        $this->assertDatabaseMissing('recipe_phases', ['id' => $phase->id]);
    }

    public function test_apply_to_zone_creates_instance(): void
    {
        $recipe = Recipe::factory()->create();
        RecipePhase::factory()->create([
            'recipe_id' => $recipe->id,
            'phase_index' => 0,
            'duration_hours' => 24,
        ]);
        $zone = Zone::factory()->create();

        $instance = $this->service->applyToZone($recipe, $zone);

        $this->assertDatabaseHas('zone_recipe_instances', [
            'zone_id' => $zone->id,
            'recipe_id' => $recipe->id,
            'current_phase_index' => 0,
        ]);
        $this->assertEquals($zone->id, $instance->zone_id);
        $this->assertEquals($recipe->id, $instance->recipe_id);
    }

    public function test_apply_to_zone_replaces_existing_instance(): void
    {
        $recipe1 = Recipe::factory()->create();
        $recipe2 = Recipe::factory()->create();
        RecipePhase::factory()->create(['recipe_id' => $recipe1->id, 'phase_index' => 0]);
        RecipePhase::factory()->create(['recipe_id' => $recipe2->id, 'phase_index' => 0]);
        $zone = Zone::factory()->create();

        $instance1 = $this->service->applyToZone($recipe1, $zone);
        $instance1Id = $instance1->id;

        $instance2 = $this->service->applyToZone($recipe2, $zone);

        $this->assertDatabaseMissing('zone_recipe_instances', ['id' => $instance1Id]);
        $this->assertDatabaseHas('zone_recipe_instances', [
            'zone_id' => $zone->id,
            'recipe_id' => $recipe2->id,
        ]);
    }

    public function test_apply_to_zone_throws_if_no_phases(): void
    {
        $recipe = Recipe::factory()->create();
        $zone = Zone::factory()->create();

        $this->expectException(\DomainException::class);
        $this->expectExceptionMessage('Recipe has no phases');

        $this->service->applyToZone($recipe, $zone);
    }
}

