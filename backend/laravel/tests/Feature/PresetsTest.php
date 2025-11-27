<?php

namespace Tests\Feature;

use App\Models\User;
use App\Models\Preset;
use App\Models\Recipe;
use App\Models\Zone;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Tests\TestCase;

class PresetsTest extends TestCase
{
    use RefreshDatabase;

    private function token(): string
    {
        $user = User::factory()->create();
        $this->actingAs($user);

        return $user->createToken('test')->plainTextToken;
    }

    public function test_presets_requires_auth(): void
    {
        $this->getJson('/api/presets')->assertStatus(401);
    }

    public function test_create_preset(): void
    {
        $token = $this->token();
        $resp = $this->withHeader('Authorization', 'Bearer '.$token)->postJson('/api/presets', [
            'name' => 'Test Preset',
            'plant_type' => 'lettuce',
            'ph_optimal_range' => ['min' => 5.5, 'max' => 6.5],
            'ec_range' => ['min' => 1.2, 'max' => 1.8],
            'growth_profile' => 'mid',
        ]);
        $resp->assertCreated()->assertJsonPath('data.name', 'Test Preset');
    }

    public function test_get_presets_list(): void
    {
        $token = $this->token();
        Preset::factory()->count(3)->create();

        $resp = $this->withHeader('Authorization', 'Bearer '.$token)
            ->getJson('/api/presets');

        $resp->assertOk()
            ->assertJsonStructure(['status', 'data' => ['data', 'current_page']]);
    }

    public function test_get_preset_details(): void
    {
        $token = $this->token();
        $recipe = Recipe::factory()->create();
        $preset = Preset::factory()->create(['default_recipe_id' => $recipe->id]);

        $resp = $this->withHeader('Authorization', 'Bearer '.$token)
            ->getJson("/api/presets/{$preset->id}");

        $resp->assertOk()
            ->assertJsonPath('data.id', $preset->id)
            ->assertJsonPath('data.name', $preset->name)
            ->assertJsonStructure(['data' => ['default_recipe']]);
    }

    public function test_update_preset(): void
    {
        $token = $this->token();
        $preset = Preset::factory()->create(['name' => 'Old Name']);

        $resp = $this->withHeader('Authorization', 'Bearer '.$token)
            ->patchJson("/api/presets/{$preset->id}", ['name' => 'New Name']);

        $resp->assertOk()
            ->assertJsonPath('data.name', 'New Name');
    }

    public function test_delete_preset_without_dependencies(): void
    {
        $token = $this->token();
        $preset = Preset::factory()->create();

        $resp = $this->withHeader('Authorization', 'Bearer '.$token)
            ->deleteJson("/api/presets/{$preset->id}");

        $resp->assertOk();
        $this->assertDatabaseMissing('presets', ['id' => $preset->id]);
    }

    public function test_delete_preset_used_in_zones_returns_error(): void
    {
        $token = $this->token();
        $preset = Preset::factory()->create();
        Zone::factory()->create(['preset_id' => $preset->id]);

        $resp = $this->withHeader('Authorization', 'Bearer '.$token)
            ->deleteJson("/api/presets/{$preset->id}");

        $resp->assertStatus(422)
            ->assertJsonPath('status', 'error');
    }
}

