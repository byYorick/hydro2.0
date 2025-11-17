<?php

namespace Tests\Unit\Services;

use App\Models\Zone;
use App\Models\ZoneRecipeInstance;
use App\Models\Recipe;
use App\Models\DeviceNode;
use App\Services\ZoneService;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Tests\TestCase;

class ZoneServiceTest extends TestCase
{
    use RefreshDatabase;

    private ZoneService $service;

    protected function setUp(): void
    {
        parent::setUp();
        $this->service = new ZoneService();
    }

    public function test_create_zone(): void
    {
        $data = [
            'name' => 'Test Zone',
            'description' => 'Test Description',
            'status' => 'RUNNING',
        ];

        $zone = $this->service->create($data);

        $this->assertInstanceOf(Zone::class, $zone);
        $this->assertEquals('Test Zone', $zone->name);
        $this->assertEquals('RUNNING', $zone->status);
        $this->assertDatabaseHas('zones', [
            'id' => $zone->id,
            'name' => 'Test Zone',
        ]);
    }

    public function test_update_zone(): void
    {
        $zone = Zone::factory()->create(['name' => 'Old Name']);

        $updated = $this->service->update($zone, ['name' => 'New Name']);

        $this->assertEquals('New Name', $updated->name);
        $this->assertDatabaseHas('zones', [
            'id' => $zone->id,
            'name' => 'New Name',
        ]);
    }

    public function test_delete_zone_without_dependencies(): void
    {
        $zone = Zone::factory()->create();

        $this->service->delete($zone);

        $this->assertDatabaseMissing('zones', ['id' => $zone->id]);
    }

    public function test_delete_zone_with_active_recipe_throws_exception(): void
    {
        $zone = Zone::factory()->create();
        $recipe = Recipe::factory()->create();
        ZoneRecipeInstance::factory()->create([
            'zone_id' => $zone->id,
            'recipe_id' => $recipe->id,
        ]);

        $this->expectException(\DomainException::class);
        $this->expectExceptionMessage('Cannot delete zone with active recipe');

        $this->service->delete($zone);
    }

    public function test_delete_zone_with_attached_nodes_throws_exception(): void
    {
        $zone = Zone::factory()->create();
        DeviceNode::factory()->create(['zone_id' => $zone->id]);

        $this->expectException(\DomainException::class);
        $this->expectExceptionMessage('Cannot delete zone with attached nodes');

        $this->service->delete($zone);
    }

    public function test_attach_recipe_to_zone(): void
    {
        $zone = Zone::factory()->create();
        $recipe = Recipe::factory()->create();

        $instance = $this->service->attachRecipe($zone, $recipe->id);

        $this->assertInstanceOf(ZoneRecipeInstance::class, $instance);
        $this->assertEquals($zone->id, $instance->zone_id);
        $this->assertEquals($recipe->id, $instance->recipe_id);
        $this->assertEquals(0, $instance->current_phase_index);
        $this->assertDatabaseHas('zone_recipe_instances', [
            'zone_id' => $zone->id,
            'recipe_id' => $recipe->id,
        ]);
    }

    public function test_attach_recipe_replaces_existing(): void
    {
        $zone = Zone::factory()->create();
        $oldRecipe = Recipe::factory()->create();
        $newRecipe = Recipe::factory()->create();

        $this->service->attachRecipe($zone, $oldRecipe->id);
        // Обновить зону, чтобы связь recipeInstance обновилась
        $zone->refresh();
        $this->service->attachRecipe($zone, $newRecipe->id);

        $this->assertDatabaseMissing('zone_recipe_instances', [
            'zone_id' => $zone->id,
            'recipe_id' => $oldRecipe->id,
        ]);
        $this->assertDatabaseHas('zone_recipe_instances', [
            'zone_id' => $zone->id,
            'recipe_id' => $newRecipe->id,
        ]);
    }

    public function test_change_phase(): void
    {
        $zone = Zone::factory()->create();
        $recipe = Recipe::factory()->create();
        // Создать фазы в рецепте
        \App\Models\RecipePhase::factory()->create([
            'recipe_id' => $recipe->id,
            'phase_index' => 0,
        ]);
        \App\Models\RecipePhase::factory()->create([
            'recipe_id' => $recipe->id,
            'phase_index' => 1,
        ]);
        $instance = ZoneRecipeInstance::factory()->create([
            'zone_id' => $zone->id,
            'recipe_id' => $recipe->id,
            'current_phase_index' => 0,
        ]);

        $updated = $this->service->changePhase($zone, 1);

        $this->assertEquals(1, $updated->current_phase_index);
    }

    public function test_change_phase_without_recipe_throws_exception(): void
    {
        $zone = Zone::factory()->create();

        $this->expectException(\DomainException::class);
        $this->expectExceptionMessage('Zone has no active recipe');

        $this->service->changePhase($zone, 1);
    }

    public function test_pause_zone(): void
    {
        $zone = Zone::factory()->create(['status' => 'RUNNING']);

        $paused = $this->service->pause($zone);

        $this->assertEquals('PAUSED', $paused->status);
    }

    public function test_pause_already_paused_zone_throws_exception(): void
    {
        $zone = Zone::factory()->create(['status' => 'PAUSED']);

        $this->expectException(\DomainException::class);
        $this->expectExceptionMessage('Zone is already paused');

        $this->service->pause($zone);
    }

    public function test_resume_zone(): void
    {
        $zone = Zone::factory()->create(['status' => 'PAUSED']);

        $resumed = $this->service->resume($zone);

        $this->assertEquals('RUNNING', $resumed->status);
    }

    public function test_resume_not_paused_zone_throws_exception(): void
    {
        $zone = Zone::factory()->create(['status' => 'RUNNING']);

        $this->expectException(\DomainException::class);
        $this->expectExceptionMessage('Zone is not paused');

        $this->service->resume($zone);
    }
}

