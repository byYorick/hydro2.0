<?php

namespace Tests\Feature;

use App\Models\User;
use App\Models\Zone;
use App\Models\Recipe;
use App\Models\RecipePhase;
use App\Models\ZoneSimulation;
use App\Models\TelemetryLast;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Illuminate\Support\Facades\Http;
use Tests\TestCase;

class SimulationControllerTest extends TestCase
{
    use RefreshDatabase;

    private User $user;
    private string $token;

    protected function setUp(): void
    {
        parent::setUp();
        $this->user = User::factory()->create([
            'password' => 'password',
            'role' => 'operator',
        ]);
        $response = $this->postJson('/api/auth/login', [
            'email' => $this->user->email,
            'password' => 'password',
        ]);
        $this->token = $response->json('data.token');
    }

    public function test_simulate_zone_endpoint(): void
    {
        $zone = Zone::factory()->create();
        $recipe = Recipe::factory()->create();
        RecipePhase::factory()->create([
            'recipe_id' => $recipe->id,
            'phase_index' => 0,
            'duration_hours' => 24,
            'targets' => [
                'ph' => 6.0,
                'ec' => 1.2,
            ],
        ]);

        // Мокаем HTTP запрос к digital-twin сервису
        Http::fake([
            'digital-twin:8003/simulate/zone' => Http::response([
                'status' => 'ok',
                'data' => [
                    'points' => [
                        ['t' => 0, 'ph' => 6.0, 'ec' => 1.2, 'temp_air' => 22.0, 'temp_water' => 20.0, 'humidity_air' => 60.0, 'phase_index' => 0],
                        ['t' => 1, 'ph' => 6.1, 'ec' => 1.21, 'temp_air' => 22.1, 'temp_water' => 20.0, 'humidity_air' => 60.1, 'phase_index' => 0],
                    ],
                    'duration_hours' => 72,
                    'step_minutes' => 10,
                ],
            ], 200),
        ]);

        $response = $this->withHeader('Authorization', 'Bearer ' . $this->token)
            ->postJson("/api/simulations/zone/{$zone->id}", [
                'scenario' => [
                    'recipe_id' => $recipe->id,
                    'initial_state' => [
                        'ph' => 6.0,
                        'ec' => 1.2,
                        'temp_air' => 22.0,
                        'temp_water' => 20.0,
                        'humidity_air' => 60.0,
                    ],
                ],
                'duration_hours' => 72,
                'step_minutes' => 10,
            ]);

        $response->assertOk()
            ->assertJsonStructure([
                'status',
                'data' => [
                    'simulation_id',
                    'status',
                    'results',
                ],
            ]);

        $this->assertEquals('ok', $response->json('status'));
        $this->assertEquals('completed', $response->json('data.status'));
        $this->assertDatabaseHas('zone_simulations', [
            'zone_id' => $zone->id,
            'status' => 'completed',
        ]);
    }

    public function test_simulate_zone_with_current_telemetry(): void
    {
        $zone = Zone::factory()->create();
        $recipe = Recipe::factory()->create();
        RecipePhase::factory()->create([
            'recipe_id' => $recipe->id,
            'phase_index' => 0,
            'duration_hours' => 24,
        ]);

        // Создаем текущую телеметрию
        TelemetryLast::create([
            'zone_id' => $zone->id,
            'metric_type' => 'ph',
            'value' => 6.2,
            'updated_at' => now(),
        ]);
        TelemetryLast::create([
            'zone_id' => $zone->id,
            'metric_type' => 'ec',
            'value' => 1.3,
            'updated_at' => now(),
        ]);

        Http::fake([
            'digital-twin:8003/simulate/zone' => Http::response([
                'status' => 'ok',
                'data' => [
                    'points' => [],
                    'duration_hours' => 72,
                    'step_minutes' => 10,
                ],
            ], 200),
        ]);

        $response = $this->withHeader('Authorization', 'Bearer ' . $this->token)
            ->postJson("/api/simulations/zone/{$zone->id}", [
                'scenario' => [
                    'recipe_id' => $recipe->id,
                ],
                'duration_hours' => 72,
            ]);

        $response->assertOk();
        $simulation = ZoneSimulation::where('zone_id', $zone->id)->first();
        $this->assertNotNull($simulation);
        $this->assertArrayHasKey('initial_state', $simulation->scenario);
        $this->assertEquals(6.2, $simulation->scenario['initial_state']['ph']);
    }

    public function test_get_simulation_results(): void
    {
        $zone = Zone::factory()->create();
        $simulation = ZoneSimulation::factory()->create([
            'zone_id' => $zone->id,
            'status' => 'completed',
            'results' => [
                'points' => [
                    ['t' => 0, 'ph' => 6.0, 'ec' => 1.2],
                ],
            ],
        ]);

        $response = $this->withHeader('Authorization', 'Bearer ' . $this->token)
            ->getJson("/api/simulations/{$simulation->id}");

        $response->assertOk()
            ->assertJsonStructure([
                'status',
                'data' => [
                    'id',
                    'zone_id',
                    'scenario',
                    'results',
                    'duration_hours',
                    'step_minutes',
                    'status',
                ],
            ]);

        $this->assertEquals('ok', $response->json('status'));
        $this->assertEquals($simulation->id, $response->json('data.id'));
        $this->assertEquals('completed', $response->json('data.status'));
    }
}
