<?php

namespace Tests\Feature;

use App\Models\GrowCycle;
use App\Models\Plant;
use App\Models\Recipe;
use App\Models\RecipeRevision;
use App\Models\RecipeRevisionPhase;
use App\Models\User;
use Tests\RefreshDatabase;
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
        RecipeRevisionPhase::factory()->create([
            'recipe_revision_id' => $revision->id,
            'phase_index' => 0,
            'temp_air_target' => 23.0,
            'humidity_target' => 62.0,
            'lighting_photoperiod_hours' => 16,
            'lighting_start_time' => '06:00:00',
            'irrigation_mode' => 'SUBSTRATE',
            'irrigation_interval_sec' => 900,
            'irrigation_duration_sec' => 15,
            'extensions' => [
                'day_night' => [
                    'temperature' => ['day' => 23.0, 'night' => 21.0],
                    'humidity' => ['day' => 62.0, 'night' => 66.0],
                ],
                'subsystems' => [
                    'irrigation' => [
                        'targets' => [
                            'system_type' => 'drip',
                        ],
                    ],
                ],
            ],
        ]);
        RecipeRevisionPhase::factory()->create([
            'recipe_revision_id' => $revision->id,
            'phase_index' => 1,
        ]);

        $resp = $this->withHeader('Authorization', 'Bearer '.$token)
            ->getJson("/api/recipes/{$recipe->id}");

        $resp->assertOk()
            ->assertJsonPath('data.id', $recipe->id)
            ->assertJsonPath('data.name', $recipe->name)
            ->assertJsonCount(2, 'data.phases')
            ->assertJsonPath('data.phases.0.targets.temp_air', 23)
            ->assertJsonPath('data.phases.0.targets.humidity_air', 62)
            ->assertJsonPath('data.phases.0.targets.irrigation.mode', 'SUBSTRATE')
            ->assertJsonPath('data.phases.0.targets.irrigation.system_type', 'drip')
            ->assertJsonPath('data.phases.0.extensions.day_night.temperature.day', 23);
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

    public function test_active_usage_returns_empty_when_no_active_cycles(): void
    {
        $token = $this->token();
        $recipe = Recipe::factory()->create();

        $resp = $this->withHeader('Authorization', 'Bearer '.$token)
            ->getJson("/api/recipes/{$recipe->id}/active-usage");

        $resp->assertOk()
            ->assertJsonPath('data.recipe_id', $recipe->id)
            ->assertJsonPath('data.count', 0)
            ->assertJsonPath('data.active_cycles', []);
    }

    public function test_active_usage_returns_running_cycles(): void
    {
        $token = $this->token();
        $recipe = Recipe::factory()->create();
        $revision = RecipeRevision::factory()->create([
            'recipe_id' => $recipe->id,
            'status' => 'PUBLISHED',
            'revision_number' => 3,
        ]);
        $cycle = GrowCycle::factory()->create([
            'recipe_id' => $recipe->id,
            'recipe_revision_id' => $revision->id,
            'status' => \App\Enums\GrowCycleStatus::RUNNING,
        ]);

        $resp = $this->withHeader('Authorization', 'Bearer '.$token)
            ->getJson("/api/recipes/{$recipe->id}/active-usage");

        $resp->assertOk()
            ->assertJsonPath('data.count', 1)
            ->assertJsonPath('data.active_cycles.0.cycle_id', $cycle->id)
            ->assertJsonPath('data.active_cycles.0.revision_id', $revision->id)
            ->assertJsonPath('data.active_cycles.0.revision_number', 3)
            ->assertJsonPath('data.active_cycles.0.status', 'RUNNING')
            ->assertJsonPath('data.active_cycles.0.zone_id', $cycle->zone_id);
    }

    public function test_active_usage_excludes_finished_and_aborted_cycles(): void
    {
        $token = $this->token();
        $recipe = Recipe::factory()->create();
        $revision = RecipeRevision::factory()->create([
            'recipe_id' => $recipe->id,
            'status' => 'PUBLISHED',
        ]);
        GrowCycle::factory()->create([
            'recipe_id' => $recipe->id,
            'recipe_revision_id' => $revision->id,
            'status' => \App\Enums\GrowCycleStatus::HARVESTED,
        ]);
        GrowCycle::factory()->create([
            'recipe_id' => $recipe->id,
            'recipe_revision_id' => $revision->id,
            'status' => \App\Enums\GrowCycleStatus::ABORTED,
        ]);

        $resp = $this->withHeader('Authorization', 'Bearer '.$token)
            ->getJson("/api/recipes/{$recipe->id}/active-usage");

        $resp->assertOk()->assertJsonPath('data.count', 0);
    }

    public function test_active_usage_includes_planned_and_paused_cycles(): void
    {
        $token = $this->token();
        $recipe = Recipe::factory()->create();
        $revision = RecipeRevision::factory()->create([
            'recipe_id' => $recipe->id,
            'status' => 'PUBLISHED',
        ]);
        GrowCycle::factory()->create([
            'recipe_id' => $recipe->id,
            'recipe_revision_id' => $revision->id,
            'status' => \App\Enums\GrowCycleStatus::PLANNED,
        ]);
        GrowCycle::factory()->create([
            'recipe_id' => $recipe->id,
            'recipe_revision_id' => $revision->id,
            'status' => \App\Enums\GrowCycleStatus::PAUSED,
        ]);

        $resp = $this->withHeader('Authorization', 'Bearer '.$token)
            ->getJson("/api/recipes/{$recipe->id}/active-usage");

        $resp->assertOk()->assertJsonPath('data.count', 2);
    }

    public function test_active_usage_requires_auth(): void
    {
        $recipe = Recipe::factory()->create();
        $this->getJson("/api/recipes/{$recipe->id}/active-usage")->assertStatus(401);
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
                'ph_target' => 5.8,
                'ph_min' => 5.6,
                'ph_max' => 6.0,
                'ec_target' => 1.4,
                'ec_min' => 1.2,
                'ec_max' => 1.6,
                'lighting_start_time' => '06:00:00',
                'irrigation_mode' => 'SUBSTRATE',
                'extensions' => [
                    'day_target' => [
                        'temp_air' => 24.0,
                        'humidity' => 60.0,
                    ],
                    'night_target' => [
                        'temp_air' => 20.0,
                        'humidity' => 70.0,
                    ],
                    'subsystems' => [
                        'irrigation' => [
                            'targets' => [
                                'system_type' => 'drip',
                            ],
                        ],
                    ],
                ],
            ]);

        $resp->assertCreated()
            ->assertJsonPath('data.name', 'Phase 1')
            ->assertJsonPath('data.targets.ph.target', 5.8)
            ->assertJsonPath('data.targets.ec.target', 1.4)
            ->assertJsonPath('data.extensions.day_night.temperature.day', 24)
            ->assertJsonPath('data.extensions.day_night.humidity.night', 70)
            ->assertJsonPath('data.extensions.subsystems.irrigation.targets.system_type', 'drip');
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

    public function test_add_phase_rejects_invalid_nutrient_ratio_sum(): void
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
                'name' => 'Phase with invalid ratio',
                'duration_hours' => 24,
                'ph_target' => 5.8,
                'ph_min' => 5.6,
                'ph_max' => 6.0,
                'ec_target' => 1.4,
                'ec_min' => 1.2,
                'ec_max' => 1.6,
                'nutrient_npk_ratio_pct' => 40,
                'nutrient_calcium_ratio_pct' => 40,
                'nutrient_magnesium_ratio_pct' => 5,
                'nutrient_micro_ratio_pct' => 10,
            ]);

        $resp->assertStatus(422)
            ->assertJsonValidationErrors(['nutrient_ratio_sum']);
    }

    public function test_add_phase_requires_all_four_nutrient_ratio_components(): void
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
                'name' => 'Phase with missing magnesium ratio',
                'duration_hours' => 24,
                'ph_target' => 5.8,
                'ph_min' => 5.6,
                'ph_max' => 6.0,
                'ec_target' => 1.4,
                'ec_min' => 1.2,
                'ec_max' => 1.6,
                'nutrient_npk_ratio_pct' => 50,
                'nutrient_calcium_ratio_pct' => 35,
                'nutrient_micro_ratio_pct' => 15,
            ]);

        $resp->assertStatus(422)
            ->assertJsonValidationErrors(['nutrient_ratio_components']);
    }

    public function test_add_phase_accepts_full_four_component_nutrition_profile(): void
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
                'name' => 'Phase full nutrition',
                'duration_hours' => 24,
                'ph_target' => 5.8,
                'ph_min' => 5.6,
                'ph_max' => 6.0,
                'ec_target' => 1.8,
                'ec_min' => 1.6,
                'ec_max' => 2.0,
                'nutrient_mode' => 'delta_ec_by_k',
                'nutrient_solution_volume_l' => 100,
                'nutrient_npk_ratio_pct' => 44,
                'nutrient_calcium_ratio_pct' => 36,
                'nutrient_magnesium_ratio_pct' => 17,
                'nutrient_micro_ratio_pct' => 3,
                'nutrient_npk_dose_ml_l' => 1.7,
                'nutrient_calcium_dose_ml_l' => 1.2,
                'nutrient_magnesium_dose_ml_l' => 0.6,
                'nutrient_micro_dose_ml_l' => 0.2,
            ]);

        $resp->assertCreated()
            ->assertJsonPath('data.nutrient_mode', 'delta_ec_by_k');
        $this->assertEquals(17.0, (float) $resp->json('data.nutrient_magnesium_ratio_pct'));

        $this->assertDatabaseHas('recipe_revision_phases', [
            'recipe_revision_id' => $revision->id,
            'name' => 'Phase full nutrition',
            'ph_target' => 5.8,
            'ec_target' => 1.8,
            'nutrient_mode' => 'delta_ec_by_k',
            'nutrient_npk_ratio_pct' => 44,
            'nutrient_calcium_ratio_pct' => 36,
            'nutrient_magnesium_ratio_pct' => 17,
            'nutrient_micro_ratio_pct' => 3,
        ]);
    }

    public function test_add_phase_requires_explicit_targets_and_bounds(): void
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
                'name' => 'Phase without targets',
                'duration_hours' => 24,
                'ph_min' => 5.6,
                'ph_max' => 6.0,
                'ec_min' => 1.2,
                'ec_max' => 1.6,
            ]);

        $resp->assertStatus(422)
            ->assertJsonValidationErrors(['ph_target', 'ec_target']);
    }

    public function test_add_phase_rejects_target_outside_bounds(): void
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
                'name' => 'Phase with invalid pH target',
                'duration_hours' => 24,
                'ph_target' => 6.4,
                'ph_min' => 5.6,
                'ph_max' => 6.0,
                'ec_target' => 1.4,
                'ec_min' => 1.2,
                'ec_max' => 1.6,
            ]);

        $resp->assertStatus(422)
            ->assertJsonValidationErrors(['ph_target']);
    }

    public function test_update_phase_rejects_target_outside_merged_bounds(): void
    {
        $token = $this->token();
        $phase = RecipeRevisionPhase::factory()->create([
            'ph_target' => 5.8,
            'ph_min' => 5.6,
            'ph_max' => 6.0,
            'ec_target' => 1.4,
            'ec_min' => 1.2,
            'ec_max' => 1.6,
        ]);

        $resp = $this->withHeader('Authorization', 'Bearer '.$token)
            ->patchJson("/api/recipe-revision-phases/{$phase->id}", [
                'ph_target' => 6.2,
            ]);

        $resp->assertStatus(422)
            ->assertJsonValidationErrors(['ph_target']);
    }

    public function test_update_phase_rejects_partial_ratio_update_when_sum_not_100(): void
    {
        $token = $this->token();
        $phase = RecipeRevisionPhase::factory()->create([
            'nutrient_npk_ratio_pct' => 44,
            'nutrient_calcium_ratio_pct' => 36,
            'nutrient_magnesium_ratio_pct' => 17,
            'nutrient_micro_ratio_pct' => 3,
        ]);

        $resp = $this->withHeader('Authorization', 'Bearer '.$token)
            ->patchJson("/api/recipe-revision-phases/{$phase->id}", [
                'nutrient_npk_ratio_pct' => 60,
            ]);

        $resp->assertStatus(422)
            ->assertJsonValidationErrors(['nutrient_ratio_sum']);
    }

    public function test_update_phase_rejects_invalid_nutrient_mode(): void
    {
        $token = $this->token();
        $phase = RecipeRevisionPhase::factory()->create([
            'nutrient_mode' => 'ratio_ec_pid',
            'nutrient_npk_ratio_pct' => 44,
            'nutrient_calcium_ratio_pct' => 36,
            'nutrient_magnesium_ratio_pct' => 17,
            'nutrient_micro_ratio_pct' => 3,
        ]);

        $resp = $this->withHeader('Authorization', 'Bearer '.$token)
            ->patchJson("/api/recipe-revision-phases/{$phase->id}", [
                'nutrient_mode' => 'legacy_ratio',
            ]);

        $resp->assertStatus(422)
            ->assertJsonValidationErrors(['nutrient_mode']);
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
