<?php

namespace Tests\Feature;

use App\Models\Plant;
use App\Models\Recipe;
use App\Models\RecipeRevision;
use App\Models\RecipeRevisionPhase;
use App\Models\TelemetryLast;
use App\Models\TelemetrySample;
use App\Models\User;
use App\Models\Zone;
use App\Services\GrowCycleService;
use Carbon\Carbon;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Tests\TestCase;

class AiControllerTest extends TestCase
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

    public function test_predict_endpoint(): void
    {
        $zone = Zone::factory()->create(['status' => 'RUNNING']);

        // Создаем телеметрию
        $now = Carbon::now();
        for ($i = 0; $i < 10; $i++) {
            TelemetrySample::create([
                'zone_id' => $zone->id,
                'metric_type' => 'ph',
                'value' => 6.0 + ($i * 0.05),
                'ts' => $now->copy()->subHours(2)->addMinutes($i * 12),
            ]);
        }

        $response = $this->withHeader('Authorization', 'Bearer '.$this->token)
            ->postJson('/api/ai/predict', [
                'zone_id' => $zone->id,
                'metric_type' => 'ph',
                'horizon_minutes' => 60,
            ]);

        $response->assertOk()
            ->assertJsonStructure([
                'status',
                'data' => [
                    'predicted_value',
                    'confidence',
                    'predicted_at',
                    'horizon_minutes',
                ],
            ]);

        $this->assertEquals('ok', $response->json('status'));
        $this->assertIsNumeric($response->json('data.predicted_value'));
        $this->assertIsNumeric($response->json('data.confidence'));
    }

    public function test_predict_endpoint_without_sufficient_data(): void
    {
        $zone = Zone::factory()->create();

        $response = $this->withHeader('Authorization', 'Bearer '.$this->token)
            ->postJson('/api/ai/predict', [
                'zone_id' => $zone->id,
                'metric_type' => 'ph',
                'horizon_minutes' => 60,
            ]);

        $response->assertStatus(422)
            ->assertJson([
                'status' => 'error',
            ]);
    }

    public function test_explain_zone_endpoint(): void
    {
        $zone = Zone::factory()->create();
        $plant = Plant::factory()->create();
        $recipe = Recipe::factory()->create();
        $revision = RecipeRevision::factory()->create([
            'recipe_id' => $recipe->id,
            'status' => 'PUBLISHED',
        ]);
        RecipeRevisionPhase::factory()->create([
            'recipe_revision_id' => $revision->id,
            'phase_index' => 0,
            'ph_target' => 6.0,
            'ec_target' => 1.2,
        ]);
        $service = app(GrowCycleService::class);
        $service->createCycle($zone, $revision, $plant->id, ['start_immediately' => true]);

        // Создаем телеметрию
        TelemetryLast::create([
            'zone_id' => $zone->id,
            'metric_type' => 'ph',
            'value' => 6.5, // выше цели
            'updated_at' => now(),
        ]);
        TelemetryLast::create([
            'zone_id' => $zone->id,
            'metric_type' => 'ec',
            'value' => 1.0, // ниже цели
            'updated_at' => now(),
        ]);

        $response = $this->withHeader('Authorization', 'Bearer '.$this->token)
            ->postJson('/api/ai/explain_zone', [
                'zone_id' => $zone->id,
            ]);

        $response->assertOk()
            ->assertJsonStructure([
                'status',
                'data' => [
                    'zone_id',
                    'zone_name',
                    'status',
                    'explanations',
                    'forecasts',
                    'telemetry',
                ],
            ]);

        $this->assertEquals('ok', $response->json('status'));
        $this->assertNotEmpty($response->json('data.explanations'));
    }

    public function test_recommend_endpoint(): void
    {
        $zone = Zone::factory()->create();
        $plant = Plant::factory()->create();
        $recipe = Recipe::factory()->create();
        $revision = RecipeRevision::factory()->create([
            'recipe_id' => $recipe->id,
            'status' => 'PUBLISHED',
        ]);
        RecipeRevisionPhase::factory()->create([
            'recipe_revision_id' => $revision->id,
            'phase_index' => 0,
            'ph_target' => 6.0,
            'ec_target' => 1.2,
        ]);
        $service = app(GrowCycleService::class);
        $service->createCycle($zone, $revision, $plant->id, ['start_immediately' => true]);

        // Создаем телеметрию с отклонениями
        TelemetryLast::create([
            'zone_id' => $zone->id,
            'metric_type' => 'ph',
            'value' => 6.5, // выше цели на 0.5
            'updated_at' => now(),
        ]);
        TelemetryLast::create([
            'zone_id' => $zone->id,
            'metric_type' => 'ec',
            'value' => 0.8, // ниже цели на 0.4
            'updated_at' => now(),
        ]);

        $response = $this->withHeader('Authorization', 'Bearer '.$this->token)
            ->postJson('/api/ai/recommend', [
                'zone_id' => $zone->id,
            ]);

        $response->assertOk()
            ->assertJsonStructure([
                'status',
                'data' => [
                    'zone_id',
                    'recommendations',
                ],
            ]);

        $recommendations = $response->json('data.recommendations');
        $this->assertNotEmpty($recommendations);
        $this->assertContains('ph_correction', array_column($recommendations, 'type'));
        $this->assertContains('ec_correction', array_column($recommendations, 'type'));
    }

    public function test_diagnostics_endpoint(): void
    {
        $zone1 = Zone::factory()->create(['status' => 'RUNNING']);
        $zone2 = Zone::factory()->create(['status' => 'online']);

        $response = $this->withHeader('Authorization', 'Bearer '.$this->token)
            ->postJson('/api/ai/diagnostics');

        $response->assertOk()
            ->assertJsonStructure([
                'status',
                'data' => [
                    'total_zones',
                    'zones',
                ],
            ]);

        $this->assertEquals('ok', $response->json('status'));
        $this->assertGreaterThanOrEqual(2, $response->json('data.total_zones'));
    }
}
