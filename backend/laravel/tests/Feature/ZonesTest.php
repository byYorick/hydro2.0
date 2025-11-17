<?php

namespace Tests\Feature;

use App\Models\User;
use App\Models\Zone;
use App\Models\Recipe;
use App\Models\ZoneRecipeInstance;
use App\Models\DeviceNode;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Tests\TestCase;

class ZonesTest extends TestCase
{
    use RefreshDatabase;

    private function token(): string
    {
        $user = User::factory()->create();
        return $user->createToken('test')->plainTextToken;
    }

    public function test_zones_requires_auth(): void
    {
        $this->getJson('/api/zones')->assertStatus(401);
    }

    public function test_create_zone(): void
    {
        $token = $this->token();
        $resp = $this->withHeader('Authorization', 'Bearer '.$token)->postJson('/api/zones', [
            'name' => 'Zone A',
            'status' => 'RUNNING',
        ]);
        $resp->assertCreated()->assertJsonPath('data.name', 'Zone A');
    }

    public function test_get_zones_list(): void
    {
        $token = $this->token();
        Zone::factory()->count(3)->create();

        $resp = $this->withHeader('Authorization', 'Bearer '.$token)
            ->getJson('/api/zones');

        $resp->assertOk()
            ->assertJsonStructure(['status', 'data' => ['data', 'current_page']]);
    }

    public function test_get_zone_details(): void
    {
        $token = $this->token();
        $zone = Zone::factory()->create();

        $resp = $this->withHeader('Authorization', 'Bearer '.$token)
            ->getJson("/api/zones/{$zone->id}");

        $resp->assertOk()
            ->assertJsonPath('data.id', $zone->id)
            ->assertJsonPath('data.name', $zone->name);
    }

    public function test_update_zone(): void
    {
        $token = $this->token();
        $zone = Zone::factory()->create(['name' => 'Old Name']);

        $resp = $this->withHeader('Authorization', 'Bearer '.$token)
            ->patchJson("/api/zones/{$zone->id}", ['name' => 'New Name']);

        $resp->assertOk()
            ->assertJsonPath('data.name', 'New Name');
    }

    public function test_delete_zone_without_dependencies(): void
    {
        $token = $this->token();
        $zone = Zone::factory()->create();

        $resp = $this->withHeader('Authorization', 'Bearer '.$token)
            ->deleteJson("/api/zones/{$zone->id}");

        $resp->assertOk();
        $this->assertDatabaseMissing('zones', ['id' => $zone->id]);
    }

    public function test_delete_zone_with_active_recipe_returns_error(): void
    {
        $token = $this->token();
        $zone = Zone::factory()->create();
        $recipe = Recipe::factory()->create();
        ZoneRecipeInstance::factory()->create([
            'zone_id' => $zone->id,
            'recipe_id' => $recipe->id,
        ]);

        $resp = $this->withHeader('Authorization', 'Bearer '.$token)
            ->deleteJson("/api/zones/{$zone->id}");

        $resp->assertStatus(422)
            ->assertJsonPath('status', 'error')
            ->assertJsonPath('message', 'Cannot delete zone with active recipe. Please detach recipe first.');
    }

    public function test_attach_recipe_to_zone(): void
    {
        $token = $this->token();
        $zone = Zone::factory()->create();
        $recipe = Recipe::factory()->create();

        $resp = $this->withHeader('Authorization', 'Bearer '.$token)
            ->postJson("/api/zones/{$zone->id}/attach-recipe", [
                'recipe_id' => $recipe->id,
            ]);

        $resp->assertOk();
        $this->assertDatabaseHas('zone_recipe_instances', [
            'zone_id' => $zone->id,
            'recipe_id' => $recipe->id,
        ]);
    }

    public function test_change_phase(): void
    {
        $token = $this->token();
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
        ZoneRecipeInstance::factory()->create([
            'zone_id' => $zone->id,
            'recipe_id' => $recipe->id,
            'current_phase_index' => 0,
        ]);

        $resp = $this->withHeader('Authorization', 'Bearer '.$token)
            ->postJson("/api/zones/{$zone->id}/change-phase", [
                'phase_index' => 1,
            ]);

        $resp->assertOk();
        $this->assertDatabaseHas('zone_recipe_instances', [
            'zone_id' => $zone->id,
            'current_phase_index' => 1,
        ]);
    }

    public function test_pause_zone(): void
    {
        $token = $this->token();
        $zone = Zone::factory()->create(['status' => 'RUNNING']);

        $resp = $this->withHeader('Authorization', 'Bearer '.$token)
            ->postJson("/api/zones/{$zone->id}/pause");

        $resp->assertOk()
            ->assertJsonPath('data.status', 'PAUSED');
    }

    public function test_resume_zone(): void
    {
        $token = $this->token();
        $zone = Zone::factory()->create(['status' => 'PAUSED']);

        $resp = $this->withHeader('Authorization', 'Bearer '.$token)
            ->postJson("/api/zones/{$zone->id}/resume");

        $resp->assertOk()
            ->assertJsonPath('data.status', 'RUNNING');
    }
}


