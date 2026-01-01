<?php

namespace Tests\Feature;

use App\Enums\GrowCycleStatus;
use App\Models\Greenhouse;
use App\Models\GrowCycle;
use App\Models\Plant;
use App\Models\Recipe;
use App\Models\RecipeRevision;
use App\Models\RecipeRevisionPhase;
use App\Models\User;
use App\Models\Zone;
use App\Services\GrowCycleService;
use Tests\RefreshDatabase;
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

    private function createRevisionWithPhases(Recipe $recipe, int $count = 1): RecipeRevision
    {
        $revision = RecipeRevision::factory()->create([
            'recipe_id' => $recipe->id,
            'status' => 'PUBLISHED',
        ]);

        for ($index = 0; $index < $count; $index++) {
            RecipeRevisionPhase::factory()->create([
                'recipe_revision_id' => $revision->id,
                'phase_index' => $index,
                'name' => 'Phase '.($index + 1),
            ]);
        }

        return $revision;
    }

    private function createGrowCycle(Zone $zone, Recipe $recipe, Plant $plant, int $phases = 1, bool $start = false): GrowCycle
    {
        $recipe->plants()->syncWithoutDetaching([$plant->id]);
        $revision = $this->createRevisionWithPhases($recipe, $phases);
        $service = app(GrowCycleService::class);

        return $service->createCycle($zone, $revision, $plant->id, ['start_immediately' => $start]);
    }

    public function test_zones_requires_auth(): void
    {
        $this->getJson('/api/zones')->assertStatus(401);
    }

    public function test_create_zone(): void
    {
        $token = $this->token();
        $greenhouse = Greenhouse::factory()->create();
        $resp = $this->withHeader('Authorization', 'Bearer '.$token)->postJson('/api/zones', [
            'name' => 'Zone A',
            'greenhouse_id' => $greenhouse->id,
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
            ->assertJsonStructure(['status', 'data']);
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
        $plant = Plant::factory()->create();
        $recipe = Recipe::factory()->create();
        $this->createGrowCycle($zone, $recipe, $plant, 1, false);

        $resp = $this->withHeader('Authorization', 'Bearer '.$token)
            ->deleteJson("/api/zones/{$zone->id}");

        $resp->assertStatus(422)
            ->assertJsonPath('status', 'error')
            ->assertJsonPath('message', 'Cannot delete zone with active grow cycle. Please finish or abort cycle first.');
    }

    public function test_attach_recipe_to_zone(): void
    {
        $token = $this->token('agronomist');
        $zone = Zone::factory()->create();
        $plant = Plant::factory()->create();
        $recipe = Recipe::factory()->create();
        $revision = $this->createRevisionWithPhases($recipe, 1);

        $resp = $this->withHeader('Authorization', 'Bearer '.$token)
            ->postJson("/api/zones/{$zone->id}/grow-cycles", [
                'recipe_revision_id' => $revision->id,
                'plant_id' => $plant->id,
                'start_immediately' => false,
            ]);

        $resp->assertStatus(201);
        $this->assertDatabaseHas('grow_cycles', [
            'zone_id' => $zone->id,
            'recipe_revision_id' => $revision->id,
            'status' => GrowCycleStatus::PLANNED->value,
        ]);
    }

    public function test_change_phase(): void
    {
        $token = $this->token('agronomist');
        $zone = Zone::factory()->create();
        $plant = Plant::factory()->create();
        $recipe = Recipe::factory()->create();
        $cycle = $this->createGrowCycle($zone, $recipe, $plant, 2, true);

        $resp = $this->withHeader('Authorization', 'Bearer '.$token)
            ->postJson("/api/grow-cycles/{$cycle->id}/advance-phase");

        $resp->assertOk();
        $cycle->refresh();
        $this->assertEquals(1, $cycle->currentPhase->phase_index);
    }

    public function test_pause_zone(): void
    {
        $token = $this->token('agronomist');
        $zone = Zone::factory()->create();
        $plant = Plant::factory()->create();
        $recipe = Recipe::factory()->create();
        $cycle = $this->createGrowCycle($zone, $recipe, $plant, 1, true);
        $cycle->update(['status' => GrowCycleStatus::RUNNING]);

        $resp = $this->withHeader('Authorization', 'Bearer '.$token)
            ->postJson("/api/grow-cycles/{$cycle->id}/pause");

        $resp->assertOk();
        $this->assertEquals(GrowCycleStatus::PAUSED->value, $cycle->fresh()->status->value);
    }

    public function test_resume_zone(): void
    {
        $token = $this->token('agronomist');
        $zone = Zone::factory()->create();
        $plant = Plant::factory()->create();
        $recipe = Recipe::factory()->create();
        $cycle = $this->createGrowCycle($zone, $recipe, $plant, 1, false);
        $cycle->update(['status' => GrowCycleStatus::PAUSED]);

        $resp = $this->withHeader('Authorization', 'Bearer '.$token)
            ->postJson("/api/grow-cycles/{$cycle->id}/resume");

        $resp->assertOk();
        $this->assertEquals(GrowCycleStatus::RUNNING->value, $cycle->fresh()->status->value);
    }

    public function test_fill_zone(): void
    {
        $token = $this->token();
        $zone = Zone::factory()->create(['status' => 'online']);
        $plant = Plant::factory()->create();
        $recipe = Recipe::factory()->create();
        $this->createGrowCycle($zone, $recipe, $plant, 1, false);

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
                'max_duration_sec' => 60,
            ]);

        $resp->assertStatus(202)
            ->assertJsonPath('status', 'ok')
            ->assertJsonPath('message', 'Fill operation queued');
    }

    public function test_drain_zone_success(): void
    {
        $token = $this->token();
        $zone = Zone::factory()->create(['status' => 'online']);
        $plant = Plant::factory()->create();
        $recipe = Recipe::factory()->create();
        $this->createGrowCycle($zone, $recipe, $plant, 1, false);

        \Illuminate\Support\Facades\Http::fake([
            '*' => \Illuminate\Support\Facades\Http::response([
                'status' => 'ok',
                'data' => [
                    'success' => true,
                    'target_level' => 0.1,
                    'final_level' => 0.1,
                    'elapsed_sec' => 45.2,
                ],
            ], 200),
        ]);

        $resp = $this->withHeader('Authorization', 'Bearer '.$token)
            ->postJson("/api/zones/{$zone->id}/drain", [
                'target_level' => 0.1,
                'max_duration_sec' => 60,
            ]);

        $resp->assertStatus(202)
            ->assertJsonPath('status', 'ok')
            ->assertJsonPath('message', 'Drain operation queued');
    }

    public function test_drain_zone_python_service_down(): void
    {
        $token = $this->token();
        $zone = Zone::factory()->create(['status' => 'online']);
        $plant = Plant::factory()->create();
        $recipe = Recipe::factory()->create();
        $this->createGrowCycle($zone, $recipe, $plant, 1, false);

        \Illuminate\Support\Facades\Http::fake([
            '*' => \Illuminate\Support\Facades\Http::response(null, 500),
        ]);

        $resp = $this->withHeader('Authorization', 'Bearer '.$token)
            ->postJson("/api/zones/{$zone->id}/drain", [
                'target_level' => 0.1,
            ]);

        $resp->assertStatus(202)
            ->assertJsonPath('status', 'ok')
            ->assertJsonPath('message', 'Drain operation queued');
    }

    public function test_next_phase_success(): void
    {
        $token = $this->token('agronomist');
        $zone = Zone::factory()->create();
        $plant = Plant::factory()->create();
        $recipe = Recipe::factory()->create();
        $cycle = $this->createGrowCycle($zone, $recipe, $plant, 2, true);

        $resp = $this->withHeader('Authorization', 'Bearer '.$token)
            ->postJson("/api/grow-cycles/{$cycle->id}/advance-phase");

        $resp->assertOk();
        $this->assertEquals(1, $cycle->fresh()->currentPhase->phase_index);
    }

    public function test_next_phase_no_current_phase(): void
    {
        $token = $this->token('agronomist');
        $zone = Zone::factory()->create();
        $cycle = GrowCycle::factory()->create([
            'zone_id' => $zone->id,
            'status' => GrowCycleStatus::RUNNING,
        ]);

        $resp = $this->withHeader('Authorization', 'Bearer '.$token)
            ->postJson("/api/grow-cycles/{$cycle->id}/advance-phase");

        $resp->assertStatus(422)
            ->assertJsonPath('status', 'error')
            ->assertJsonPath('message', 'Cycle has no current phase');
    }

    public function test_next_phase_last_phase(): void
    {
        $token = $this->token('agronomist');
        $zone = Zone::factory()->create();
        $plant = Plant::factory()->create();
        $recipe = Recipe::factory()->create();
        $cycle = $this->createGrowCycle($zone, $recipe, $plant, 1, true);

        $resp = $this->withHeader('Authorization', 'Bearer '.$token)
            ->postJson("/api/grow-cycles/{$cycle->id}/advance-phase");

        $resp->assertStatus(422)
            ->assertJsonPath('status', 'error')
            ->assertJsonPath('message', 'No next phase available');
    }

    public function test_zone_show_includes_phase_progress(): void
    {
        $token = $this->token();
        $zone = Zone::factory()->create();
        $plant = Plant::factory()->create();
        $recipe = Recipe::factory()->create();
        $cycle = $this->createGrowCycle($zone, $recipe, $plant, 1, true);

        $resp = $this->withHeader('Authorization', 'Bearer '.$token)
            ->getJson("/api/zones/{$zone->id}");

        $resp->assertOk()
            ->assertJsonPath('status', 'ok');

        $data = $resp->json('data');
        $this->assertArrayHasKey('active_grow_cycle', $data);
    }

    public function test_phase_progress_calculation(): void
    {
        $token = $this->token('agronomist');
        $zone = Zone::factory()->create();
        $plant = Plant::factory()->create();
        $recipe = Recipe::factory()->create();
        $cycle = $this->createGrowCycle($zone, $recipe, $plant, 2, true);

        $resp = $this->withHeader('Authorization', 'Bearer '.$token)
            ->getJson("/api/zones/{$zone->id}/grow-cycle");

        $resp->assertOk();
        $this->assertNotNull($resp->json('data.cycle.progress.overall_pct'));
    }
}
