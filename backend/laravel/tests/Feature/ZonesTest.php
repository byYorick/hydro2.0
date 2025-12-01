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

    private function token(string $role = 'operator'): string
    {
        $user = User::factory()->create(['role' => $role]);
        $this->actingAs($user);

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

    public function test_fill_zone(): void
    {
        $token = $this->token();
        $zone = Zone::factory()->create();

        \Illuminate\Support\Facades\Http::fake([
            '*' => \Illuminate\Support\Facades\Http::response([
                'status' => 'ok',
                'data' => [
                    'success' => true,
                    'target_level' => 0.9,
                    'final_level' => 0.9,
                    'elapsed_sec' => 30.5,
                ],
            ], 200),
        ]);

        $resp = $this->withHeader('Authorization', 'Bearer '.$token)
            ->postJson("/api/zones/{$zone->id}/fill", [
                'target_level' => 0.9,
            ]);

        $resp->assertOk()
            ->assertJsonPath('status', 'ok')
            ->assertJsonPath('data.success', true)
            ->assertJsonPath('data.target_level', 0.9);
    }

    public function test_fill_zone_validation_error(): void
    {
        $token = $this->token();
        $zone = Zone::factory()->create();

        // target_level слишком низкий
        $resp = $this->withHeader('Authorization', 'Bearer '.$token)
            ->postJson("/api/zones/{$zone->id}/fill", [
                'target_level' => 0.05,
            ]);

        $resp->assertStatus(422);
    }

    public function test_fill_zone_with_max_duration(): void
    {
        $token = $this->token();
        $zone = Zone::factory()->create();

        \Illuminate\Support\Facades\Http::fake([
            '*' => \Illuminate\Support\Facades\Http::response([
                'status' => 'ok',
                'data' => ['success' => true],
            ], 200),
        ]);

        $resp = $this->withHeader('Authorization', 'Bearer '.$token)
            ->postJson("/api/zones/{$zone->id}/fill", [
                'target_level' => 0.9,
                'max_duration_sec' => 120,
            ]);

        $resp->assertOk();
    }

    public function test_drain_zone(): void
    {
        $token = $this->token();
        $zone = Zone::factory()->create();

        \Illuminate\Support\Facades\Http::fake([
            '*' => \Illuminate\Support\Facades\Http::response([
                'status' => 'ok',
                'data' => [
                    'success' => true,
                    'target_level' => 0.1,
                    'final_level' => 0.1,
                    'elapsed_sec' => 25.3,
                ],
            ], 200),
        ]);

        $resp = $this->withHeader('Authorization', 'Bearer '.$token)
            ->postJson("/api/zones/{$zone->id}/drain", [
                'target_level' => 0.1,
            ]);

        $resp->assertOk()
            ->assertJsonPath('status', 'ok')
            ->assertJsonPath('data.success', true)
            ->assertJsonPath('data.target_level', 0.1);
    }

    public function test_drain_zone_validation_error(): void
    {
        $token = $this->token();
        $zone = Zone::factory()->create();

        // target_level слишком высокий
        $resp = $this->withHeader('Authorization', 'Bearer '.$token)
            ->postJson("/api/zones/{$zone->id}/drain", [
                'target_level' => 0.95,
            ]);

        $resp->assertStatus(422);
    }

    public function test_drain_zone_python_service_error(): void
    {
        $token = $this->token();
        $zone = Zone::factory()->create();

        \Illuminate\Support\Facades\Http::fake([
            '*' => \Illuminate\Support\Facades\Http::response([
                'detail' => 'Fill operation failed: Zone not found',
            ], 500),
        ]);

        $resp = $this->withHeader('Authorization', 'Bearer '.$token)
            ->postJson("/api/zones/{$zone->id}/drain", [
                'target_level' => 0.1,
            ]);

        $resp->assertStatus(422)
            ->assertJsonPath('status', 'error');
    }

    public function test_next_phase_success(): void
    {
        $token = $this->token();
        $zone = Zone::factory()->create();
        $recipe = Recipe::factory()->create();
        
        // Создать фазы в рецепте
        \App\Models\RecipePhase::factory()->create([
            'recipe_id' => $recipe->id,
            'phase_index' => 0,
            'duration_hours' => 24,
        ]);
        \App\Models\RecipePhase::factory()->create([
            'recipe_id' => $recipe->id,
            'phase_index' => 1,
            'duration_hours' => 48,
        ]);
        
        ZoneRecipeInstance::factory()->create([
            'zone_id' => $zone->id,
            'recipe_id' => $recipe->id,
            'current_phase_index' => 0,
        ]);

        $resp = $this->withHeader('Authorization', 'Bearer '.$token)
            ->postJson("/api/zones/{$zone->id}/next-phase");

        $resp->assertOk()
            ->assertJsonPath('status', 'ok');
        
        $this->assertDatabaseHas('zone_recipe_instances', [
            'zone_id' => $zone->id,
            'current_phase_index' => 1,
        ]);
    }

    public function test_next_phase_no_recipe(): void
    {
        $token = $this->token();
        $zone = Zone::factory()->create();

        $resp = $this->withHeader('Authorization', 'Bearer '.$token)
            ->postJson("/api/zones/{$zone->id}/next-phase");

        $resp->assertStatus(422)
            ->assertJsonPath('status', 'error')
            ->assertJsonPath('message', 'Zone has no active recipe');
    }

    public function test_next_phase_last_phase(): void
    {
        $token = $this->token();
        $zone = Zone::factory()->create();
        $recipe = Recipe::factory()->create();
        
        // Создать только одну фазу
        \App\Models\RecipePhase::factory()->create([
            'recipe_id' => $recipe->id,
            'phase_index' => 0,
            'duration_hours' => 24,
        ]);
        
        ZoneRecipeInstance::factory()->create([
            'zone_id' => $zone->id,
            'recipe_id' => $recipe->id,
            'current_phase_index' => 0,
        ]);

        $resp = $this->withHeader('Authorization', 'Bearer '.$token)
            ->postJson("/api/zones/{$zone->id}/next-phase");

        $resp->assertStatus(422)
            ->assertJsonPath('status', 'error')
            ->assertJsonPath('message', 'No next phase available. Current phase is 0, max phase is 0');
    }

    public function test_zone_show_includes_phase_progress(): void
    {
        $token = $this->token();
        $zone = Zone::factory()->create();
        $recipe = Recipe::factory()->create();
        
        // Создать фазу в рецепте
        \App\Models\RecipePhase::factory()->create([
            'recipe_id' => $recipe->id,
            'phase_index' => 0,
            'duration_hours' => 24,
        ]);
        
        ZoneRecipeInstance::factory()->create([
            'zone_id' => $zone->id,
            'recipe_id' => $recipe->id,
            'current_phase_index' => 0,
            'started_at' => now()->subHours(12), // Начали 12 часов назад, фаза длится 24 часа
        ]);

        $resp = $this->withHeader('Authorization', 'Bearer '.$token)
            ->getJson("/api/zones/{$zone->id}");

        $resp->assertOk()
            ->assertJsonPath('status', 'ok');
        
        $data = $resp->json('data');
        $this->assertArrayHasKey('recipe_instance', $data);
        
        if (isset($data['recipe_instance'])) {
            $this->assertArrayHasKey('phase_progress', $data['recipe_instance']);
            // Прогресс должен быть около 50% (12 часов из 24)
            $progress = $data['recipe_instance']['phase_progress'];
            $this->assertIsFloat($progress);
            $this->assertGreaterThanOrEqual(0, $progress);
            $this->assertLessThanOrEqual(100, $progress);
        }
    }

    public function test_phase_progress_calculation(): void
    {
        $zone = Zone::factory()->create();
        $recipe = Recipe::factory()->create();
        
        // Создать две фазы
        \App\Models\RecipePhase::factory()->create([
            'recipe_id' => $recipe->id,
            'phase_index' => 0,
            'duration_hours' => 24,
        ]);
        \App\Models\RecipePhase::factory()->create([
            'recipe_id' => $recipe->id,
            'phase_index' => 1,
            'duration_hours' => 48,
        ]);
        
        // Создать instance, начатый 30 часов назад (24 часа первой фазы + 6 часов второй)
        $instance = ZoneRecipeInstance::factory()->create([
            'zone_id' => $zone->id,
            'recipe_id' => $recipe->id,
            'current_phase_index' => 1,
            'started_at' => now()->subHours(30),
        ]);
        
        // Загрузить связанные данные для вычисления прогресса
        $instance->load('recipe.phases');
        
        // Прогресс второй фазы должен быть около 12.5% (6 часов из 48)
        $progress = $instance->phase_progress;
        $this->assertIsFloat($progress);
        $this->assertGreaterThan(10, $progress);
        $this->assertLessThan(15, $progress);
    }
}


