<?php

namespace Tests\Feature;

use App\Models\Recipe;
use App\Models\User;
use App\Models\Zone;
use App\Models\ZoneSimulation;
use Inertia\Testing\AssertableInertia;
use Tests\RefreshDatabase;
use Tests\TestCase;

class ZoneSimulationPageTest extends TestCase
{
    use RefreshDatabase;

    public function test_zone_simulation_page_includes_active_simulation_by_source_zone(): void
    {
        $user = User::factory()->create(['role' => 'admin']);
        $sourceZone = Zone::factory()->create();
        $simulationZone = Zone::factory()->create();
        $recipe = Recipe::factory()->create();

        $simulation = ZoneSimulation::factory()->create([
            'zone_id' => $simulationZone->id,
            'status' => 'running',
            'scenario' => [
                'recipe_id' => $recipe->id,
                'simulation' => [
                    'source_zone_id' => $sourceZone->id,
                    'sim_zone_id' => $simulationZone->id,
                ],
            ],
        ]);

        $response = $this->actingAs($user)->get("/zones/{$sourceZone->id}/simulation");

        $response->assertStatus(200)
            ->assertInertia(function (AssertableInertia $page) use ($simulation) {
                $page->component('Zones/Simulation')
                    ->where('active_simulation.id', $simulation->id)
                    ->where('active_simulation.status', 'running');
            });
    }
}
