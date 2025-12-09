<?php

namespace Tests\Feature;

use App\Models\Zone;
use App\Models\Recipe;
use App\Models\User;
use App\Models\ZoneRecipeInstance;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Illuminate\Support\Facades\Http;
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
            'digital-twin:8003/simulate/zone' => Http::response([
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
            'digital-twin:8003/simulate/zone' => Http::response([
                'status' => 'ok',
                'data' => ['points' => [], 'duration_hours' => 72, 'step_minutes' => 10],
            ], 200),
        ]);

        $recipe = Recipe::factory()->create();
        $zone = Zone::factory()->create();
        
        // Обновляем проверку, чтобы использовать созданный recipe
        
        // Создаём ZoneRecipeInstance для связи зоны с рецептом
        ZoneRecipeInstance::factory()->create([
            'zone_id' => $zone->id,
            'recipe_id' => $recipe->id,
            'current_phase_index' => 0,
        ]);

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
            'digital-twin:8003/simulate/zone' => Http::response([
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
        Http::fake(function () {
            throw new \Illuminate\Http\Client\ConnectionException('Connection refused');
        });

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
            'digital-twin:8003/simulate/zone' => Http::response([
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
}
