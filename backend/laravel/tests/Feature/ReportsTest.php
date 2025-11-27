<?php

namespace Tests\Feature;

use App\Models\User;
use App\Models\Recipe;
use App\Models\Zone;
use App\Models\RecipeAnalytics;
use App\Models\Harvest;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Tests\TestCase;

class ReportsTest extends TestCase
{
    use RefreshDatabase;

    private function token(): string
    {
        $user = User::factory()->create();
        $this->actingAs($user);

        return $user->createToken('test')->plainTextToken;
    }

    public function test_recipe_analytics_requires_auth(): void
    {
        $recipe = Recipe::factory()->create();
        $this->getJson("/api/recipes/{$recipe->id}/analytics")->assertStatus(401);
    }

    public function test_get_recipe_analytics(): void
    {
        $token = $this->token();
        $recipe = Recipe::factory()->create();
        $zone = Zone::factory()->create();
        RecipeAnalytics::factory()->count(2)->create([
            'recipe_id' => $recipe->id,
            'zone_id' => $zone->id,
        ]);

        $resp = $this->withHeader('Authorization', 'Bearer '.$token)
            ->getJson("/api/recipes/{$recipe->id}/analytics");

        $resp->assertOk()
            ->assertJsonStructure(['status', 'data', 'stats']);
    }

    public function test_get_zone_harvests(): void
    {
        $token = $this->token();
        $zone = Zone::factory()->create();
        $recipe = Recipe::factory()->create();
        Harvest::factory()->count(3)->create([
            'zone_id' => $zone->id,
            'recipe_id' => $recipe->id,
        ]);

        $resp = $this->withHeader('Authorization', 'Bearer '.$token)
            ->getJson("/api/zones/{$zone->id}/harvests");

        $resp->assertOk()
            ->assertJsonStructure(['status', 'data', 'stats']);
    }

    public function test_create_harvest(): void
    {
        $token = $this->token();
        $zone = Zone::factory()->create();
        $recipe = Recipe::factory()->create();

        $resp = $this->withHeader('Authorization', 'Bearer '.$token)
            ->postJson('/api/harvests', [
                'zone_id' => $zone->id,
                'recipe_id' => $recipe->id,
                'harvest_date' => now()->toDateString(),
                'yield_weight_kg' => 5.5,
                'yield_count' => 10,
                'quality_score' => 8.5,
            ]);

        $resp->assertCreated()
            ->assertJsonPath('data.yield_weight_kg', '5.50');
    }

    public function test_compare_recipes(): void
    {
        $token = $this->token();
        $recipe1 = Recipe::factory()->create();
        $recipe2 = Recipe::factory()->create();
        $zone = Zone::factory()->create();

        RecipeAnalytics::factory()->create([
            'recipe_id' => $recipe1->id,
            'zone_id' => $zone->id,
            'efficiency_score' => 85.5,
        ]);

        RecipeAnalytics::factory()->create([
            'recipe_id' => $recipe2->id,
            'zone_id' => $zone->id,
            'efficiency_score' => 92.3,
        ]);

        $resp = $this->withHeader('Authorization', 'Bearer '.$token)
            ->postJson('/api/recipes/comparison', [
                'recipe_ids' => [$recipe1->id, $recipe2->id],
            ]);

        $resp->assertOk()
            ->assertJsonStructure(['status', 'data']);
    }
}

