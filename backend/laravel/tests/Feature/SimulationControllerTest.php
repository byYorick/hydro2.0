<?php

namespace Tests\Feature;

use App\Models\Plant;
use App\Models\Recipe;
use App\Models\RecipeRevision;
use App\Models\RecipeRevisionPhase;
use App\Models\User;
use App\Models\Zone;
use App\Models\ZoneSimulation;
use App\Services\GrowCycleService;
use Tests\RefreshDatabase;
use Illuminate\Support\Carbon;
use Illuminate\Support\Facades\Cache;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Http;
use Illuminate\Support\Str;
use Tests\TestCase;

class SimulationControllerTest extends TestCase
{
    use RefreshDatabase;

    protected User $user;

    protected function setUp(): void
    {
        parent::setUp();

        // Создаём пользователя для аутентификации с ролью operator для мутационных операций
        $this->user = User::factory()->create(['role' => 'operator']);
    }

    public function test_simulate_zone_requires_authentication(): void
    {
        $zone = Zone::factory()->create();

        $response = $this->postJson("/api/zones/{$zone->id}/simulate", [
            'duration_hours' => 72,
            'step_minutes' => 10,
        ]);

        $response->assertStatus(401);
    }

    public function test_simulate_zone_validates_input(): void
    {
        $zone = Zone::factory()->create();

        $response = $this->actingAs($this->user)
            ->postJson("/api/zones/{$zone->id}/simulate", [
                'duration_hours' => 1000, // Превышает максимум 720
                'step_minutes' => 100,   // Превышает максимум 60
            ]);

        $response->assertStatus(422);
        $response->assertJsonValidationErrors(['duration_hours', 'step_minutes']);
    }

    public function test_simulate_zone_success(): void
    {
        Http::fake([
            'http://digital-twin:8003/simulate/zone' => Http::response([
                'status' => 'ok',
                'data' => [
                    'points' => [
                        ['t' => 0, 'ph' => 6.0, 'ec' => 1.2, 'temp_air' => 22.0, 'temp_water' => 20.0, 'humidity_air' => 60.0, 'phase_index' => 0],
                        ['t' => 0.17, 'ph' => 6.1, 'ec' => 1.3, 'temp_air' => 22.1, 'temp_water' => 20.0, 'humidity_air' => 60.1, 'phase_index' => 0],
                    ],
                    'duration_hours' => 24,
                    'step_minutes' => 10,
                ],
            ], 200),
        ]);

        $recipe = Recipe::factory()->create();
        $zone = Zone::factory()->create();

        $response = $this->actingAs($this->user)
            ->postJson("/api/zones/{$zone->id}/simulate", [
                'duration_hours' => 24,
                'step_minutes' => 10,
                'recipe_id' => $recipe->id,
                'initial_state' => [
                    'ph' => 6.0,
                    'ec' => 1.2,
                    'temp_air' => 22.0,
                ],
            ]);

        // Симуляция выполняется асинхронно, возвращает 202 Accepted
        $response->assertStatus(202);
        $response->assertJson([
            'status' => 'ok',
        ]);
        $response->assertJsonStructure([
            'status',
            'data' => [
                'job_id',
                'status',
                'message',
            ],
        ]);

        // Симуляция выполняется асинхронно, поэтому проверяем только структуру ответа
        // Запрос к Digital Twin будет отправлен в job
    }

    public function test_simulate_zone_uses_zone_active_recipe_if_no_recipe_id_provided(): void
    {
        Http::fake([
            'http://digital-twin:8003/simulate/zone' => Http::response([
                'status' => 'ok',
                'data' => ['points' => [], 'duration_hours' => 72, 'step_minutes' => 10],
            ], 200),
        ]);

        $plant = Plant::factory()->create();
        $recipe = Recipe::factory()->create();
        $revision = RecipeRevision::factory()->create([
            'recipe_id' => $recipe->id,
            'status' => 'PUBLISHED',
        ]);
        RecipeRevisionPhase::factory()->create([
            'recipe_revision_id' => $revision->id,
            'phase_index' => 0,
        ]);
        $zone = Zone::factory()->create();

        $service = app(GrowCycleService::class);
        $service->createCycle($zone, $revision, $plant->id, ['start_immediately' => true]);

        $response = $this->actingAs($this->user)
            ->postJson("/api/zones/{$zone->id}/simulate", [
                'duration_hours' => 72,
                'step_minutes' => 10,
            ]);

        // Симуляция выполняется асинхронно, возвращает 202 Accepted
        $response->assertStatus(202);
        // Запрос к Digital Twin будет отправлен в job
    }

    public function test_simulate_zone_handles_digital_twin_error(): void
    {
        Http::fake([
            'http://digital-twin:8003/simulate/zone' => Http::response([
                'status' => 'error',
                'message' => 'Recipe not found',
            ], 404),
        ]);

        $zone = Zone::factory()->create();

        $response = $this->actingAs($this->user)
            ->postJson("/api/zones/{$zone->id}/simulate", [
                'duration_hours' => 72,
                'step_minutes' => 10,
            ]);

        // Симуляция ставится в очередь асинхронно, ошибка обрабатывается в job
        $response->assertStatus(202);
        $response->assertJson([
            'status' => 'ok',
        ]);
        $data = $response->json('data');
        $this->assertNotNull($data);
        $this->assertStringContainsString('queued', $data['message'] ?? '');
    }

    public function test_simulate_zone_handles_connection_error(): void
    {
        Http::fake([
            'http://digital-twin:8003/simulate/zone' => function () {
                throw new \Illuminate\Http\Client\ConnectionException('Connection refused');
            },
        ]);

        $zone = Zone::factory()->create();

        $response = $this->actingAs($this->user)
            ->postJson("/api/zones/{$zone->id}/simulate", [
                'duration_hours' => 72,
                'step_minutes' => 10,
            ]);

        // Симуляция ставится в очередь асинхронно, ошибка подключения обрабатывается в job
        $response->assertStatus(202);
        $response->assertJson([
            'status' => 'ok',
        ]);
        $data = $response->json('data');
        $this->assertNotNull($data);
        $this->assertStringContainsString('queued', $data['message'] ?? '');
    }

    public function test_simulate_zone_with_minimal_parameters(): void
    {
        Http::fake([
            'http://digital-twin:8003/simulate/zone' => Http::response([
                'status' => 'ok',
                'data' => ['points' => [], 'duration_hours' => 72, 'step_minutes' => 10],
            ], 200),
        ]);

        $zone = Zone::factory()->create();

        $response = $this->actingAs($this->user)
            ->postJson("/api/zones/{$zone->id}/simulate", [
                'duration_hours' => 72,
                'step_minutes' => 10,
            ]);

        // Симуляция выполняется асинхронно, возвращает 202 Accepted
        $response->assertStatus(202);

        // Симуляция выполняется асинхронно, дефолтные значения будут использованы в job
    }

    public function test_show_simulation_includes_progress_for_live_run(): void
    {
        $zone = Zone::factory()->create();

        $now = now();
        Carbon::setTestNow($now);
        $startedAt = $now->copy()->subMinutes(5)->toIso8601String();

        $simulation = ZoneSimulation::create([
            'zone_id' => $zone->id,
            'scenario' => [
                'recipe_id' => 1,
                'simulation' => [
                    'real_started_at' => $startedAt,
                    'sim_started_at' => $startedAt,
                    'real_duration_minutes' => 10,
                    'time_scale' => 12,
                ],
            ],
            'duration_hours' => 2,
            'step_minutes' => 10,
            'status' => 'running',
        ]);

        $jobId = 'sim_test_progress';
        Cache::put("simulation:{$jobId}", [
            'status' => 'processing',
            'started_at' => $startedAt,
            'simulation_id' => $simulation->id,
            'sim_duration_minutes' => 10,
        ], 3600);

        $response = $this->actingAs($this->user)
            ->getJson("/api/simulations/{$jobId}");

        $response->assertStatus(200);
        $response->assertJsonPath('data.status', 'processing');
        $progress = $response->json('data.progress');
        $this->assertNotNull($progress);
        $this->assertGreaterThan(0.45, $progress);
        $this->assertLessThan(0.55, $progress);
        $response->assertJsonPath('data.progress_source', 'timer');

        Carbon::setTestNow();
    }

    public function test_show_simulation_progress_uses_last_action(): void
    {
        $zone = Zone::factory()->create();

        $now = now();
        Carbon::setTestNow($now);
        $startedAt = $now->copy()->subMinutes(10);
        $actionAt = $now->copy()->subMinutes(2);

        $simulation = ZoneSimulation::create([
            'zone_id' => $zone->id,
            'scenario' => [
                'recipe_id' => 1,
                'simulation' => [
                    'real_started_at' => $startedAt->toIso8601String(),
                    'sim_started_at' => $startedAt->toIso8601String(),
                    'real_duration_minutes' => 20,
                    'time_scale' => 12,
                ],
            ],
            'duration_hours' => 2,
            'step_minutes' => 10,
            'status' => 'running',
        ]);

        DB::table('commands')->insert([
            'zone_id' => $zone->id,
            'cmd' => 'dose',
            'cmd_id' => (string) Str::uuid(),
            'status' => 'DONE',
            'created_at' => $actionAt,
            'updated_at' => $actionAt,
        ]);

        $jobId = 'sim_test_actions';
        Cache::put("simulation:{$jobId}", [
            'status' => 'processing',
            'started_at' => $startedAt->toIso8601String(),
            'simulation_id' => $simulation->id,
            'sim_duration_minutes' => 20,
        ], 3600);

        $response = $this->actingAs($this->user)
            ->getJson("/api/simulations/{$jobId}");

        $response->assertStatus(200);
        $response->assertJsonPath('data.progress_source', 'actions');
        $progress = $response->json('data.progress');
        $this->assertNotNull($progress);
        $this->assertGreaterThan(0.35, $progress);
        $this->assertLessThan(0.45, $progress);
        $response->assertJsonPath('data.actions.0.kind', 'command');

        Carbon::setTestNow();
    }
}
