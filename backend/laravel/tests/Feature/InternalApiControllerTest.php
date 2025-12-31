<?php

namespace Tests\Feature;

use App\Models\GrowCycle;
use App\Models\GrowCyclePhase;
use App\Models\Recipe;
use App\Models\RecipeRevision;
use App\Models\RecipeRevisionPhase;
use App\Models\Zone;
use App\Enums\GrowCycleStatus;
use Illuminate\Foundation\Testing\RefreshDatabase;
use PHPUnit\Framework\Attributes\Test;
use Tests\TestCase;

class InternalApiControllerTest extends TestCase
{
    use RefreshDatabase;

    private string $apiToken;

    protected function setUp(): void
    {
        parent::setUp();
        // Используем токен из .env или создаем тестовый
        $this->apiToken = env('LARAVEL_API_TOKEN', 'test-python-service-token');
    }

    #[Test]
    public function it_returns_effective_targets_batch_for_multiple_cycles()
    {
        // Примечание: InternalApiController принимает zone_ids, а не grow_cycle_ids
        // Но для тестирования EffectiveTargetsService можно использовать прямой вызов
        $zone1 = Zone::factory()->create();
        $zone2 = Zone::factory()->create();
        $recipe = Recipe::factory()->create();
        $revision = RecipeRevision::factory()->create([
            'recipe_id' => $recipe->id,
            'status' => 'PUBLISHED',
        ]);

        $phase = RecipeRevisionPhase::factory()->create([
            'recipe_revision_id' => $revision->id,
            'phase_index' => 0,
            'name' => 'Test Phase',
            'ph_target' => 6.0,
            'ph_min' => 5.8,
            'ph_max' => 6.2,
            'ec_target' => 1.5,
        ]);

        $cycle1 = GrowCycle::factory()->create([
            'zone_id' => $zone1->id,
            'recipe_revision_id' => $revision->id,
            'status' => GrowCycleStatus::RUNNING,
        ]);

        $cycle2 = GrowCycle::factory()->create([
            'zone_id' => $zone2->id,
            'recipe_revision_id' => $revision->id,
            'status' => GrowCycleStatus::RUNNING,
        ]);

        $snapshotPhase1 = GrowCyclePhase::factory()->create([
            'grow_cycle_id' => $cycle1->id,
            'recipe_revision_phase_id' => $phase->id,
            'phase_index' => 0,
            'name' => 'Test Phase',
            'ph_target' => 6.0,
            'ph_min' => 5.8,
            'ph_max' => 6.2,
            'ec_target' => 1.5,
        ]);

        $snapshotPhase2 = GrowCyclePhase::factory()->create([
            'grow_cycle_id' => $cycle2->id,
            'recipe_revision_phase_id' => $phase->id,
            'phase_index' => 0,
            'name' => 'Test Phase',
            'ph_target' => 6.0,
            'ph_min' => 5.8,
            'ph_max' => 6.2,
            'ec_target' => 1.5,
        ]);

        $cycle1->update(['current_phase_id' => $snapshotPhase1->id]);
        $cycle2->update(['current_phase_id' => $snapshotPhase2->id]);

        // Тестируем через zone_ids (как в реальном API)
        $response = $this->withHeaders([
            'Authorization' => "Bearer {$this->apiToken}",
        ])->postJson('/api/internal/effective-targets/batch', [
            'zone_ids' => [$zone1->id, $zone2->id],
        ]);

        $response->assertStatus(200)
            ->assertJsonStructure([
                'status',
                'data' => [
                    $zone1->id => [
                        'cycle_id',
                        'zone_id',
                        'phase',
                        'targets',
                    ],
                    $zone2->id => [
                        'cycle_id',
                        'zone_id',
                        'phase',
                        'targets',
                    ],
                ],
            ]);

        $data = $response->json('data');
        $this->assertArrayHasKey($zone1->id, $data);
        $this->assertArrayHasKey($zone2->id, $data);
        $this->assertNotNull($data[$zone1->id]);
        $this->assertNotNull($data[$zone2->id]);
        $this->assertEquals(6.0, $data[$zone1->id]['targets']['ph']['target']);
        $this->assertEquals(6.0, $data[$zone2->id]['targets']['ph']['target']);
    }

    #[Test]
    public function it_validates_zone_ids()
    {
        $response = $this->withHeaders([
            'Authorization' => "Bearer {$this->apiToken}",
        ])->postJson('/api/internal/effective-targets/batch', [
            'zone_ids' => [99999, 99998], // Несуществующие ID
        ]);

        $response->assertStatus(422);
    }

    #[Test]
    public function it_requires_authentication()
    {
        $response = $this->postJson('/api/internal/effective-targets/batch', [
            'grow_cycle_ids' => [1],
        ]);

        $response->assertStatus(401);
    }
}
