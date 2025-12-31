<?php

namespace Tests\Unit;

use App\Models\GrowCycle;
use App\Models\GrowCyclePhase;
use App\Models\GrowCycleOverride;
use App\Models\Recipe;
use App\Models\RecipeRevision;
use App\Models\RecipeRevisionPhase;
use App\Models\Zone;
use App\Services\EffectiveTargetsService;
use App\Enums\GrowCycleStatus;
use Illuminate\Foundation\Testing\RefreshDatabase;
use PHPUnit\Framework\Attributes\Test;
use Tests\TestCase;

class EffectiveTargetsServiceTest extends TestCase
{
    use RefreshDatabase;

    private EffectiveTargetsService $service;

    protected function setUp(): void
    {
        parent::setUp();
        $this->service = app(EffectiveTargetsService::class);
    }

    #[Test]
    public function it_returns_effective_targets_with_correct_structure()
    {
        $zone = Zone::factory()->create();
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
            'ec_min' => 1.3,
            'ec_max' => 1.7,
            'irrigation_mode' => 'SUBSTRATE',
            'irrigation_interval_sec' => 3600,
            'irrigation_duration_sec' => 300,
        ]);

        $cycle = GrowCycle::factory()->create([
            'zone_id' => $zone->id,
            'recipe_revision_id' => $revision->id,
            'status' => GrowCycleStatus::RUNNING,
        ]);

        // Создаем снапшот фазы
        $snapshotPhase = GrowCyclePhase::factory()->create([
            'grow_cycle_id' => $cycle->id,
            'recipe_revision_phase_id' => $phase->id,
            'phase_index' => 0,
            'name' => 'Test Phase',
            'ph_target' => 6.0,
            'ph_min' => 5.8,
            'ph_max' => 6.2,
            'ec_target' => 1.5,
            'ec_min' => 1.3,
            'ec_max' => 1.7,
        ]);

        $cycle->update(['current_phase_id' => $snapshotPhase->id]);

        $result = $this->service->getEffectiveTargets($cycle->id);

        // Проверяем структуру ответа
        $this->assertArrayHasKey('cycle_id', $result);
        $this->assertArrayHasKey('zone_id', $result);
        $this->assertArrayHasKey('phase', $result);
        $this->assertArrayHasKey('targets', $result);

        // Проверяем структуру phase
        $this->assertArrayHasKey('id', $result['phase']);
        $this->assertArrayHasKey('name', $result['phase']);
        $this->assertArrayHasKey('started_at', $result['phase']);
        $this->assertArrayHasKey('due_at', $result['phase']);

        // Проверяем структуру targets
        $this->assertArrayHasKey('ph', $result['targets']);
        $this->assertArrayHasKey('ec', $result['targets']);

        // Проверяем структуру ph
        $this->assertArrayHasKey('target', $result['targets']['ph']);
        $this->assertArrayHasKey('min', $result['targets']['ph']);
        $this->assertArrayHasKey('max', $result['targets']['ph']);

        // Проверяем значения
        $this->assertEquals(6.0, $result['targets']['ph']['target']);
        $this->assertEquals(5.8, $result['targets']['ph']['min']);
        $this->assertEquals(6.2, $result['targets']['ph']['max']);
    }

    #[Test]
    public function it_applies_overrides_to_targets()
    {
        $zone = Zone::factory()->create();
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
        ]);

        $cycle = GrowCycle::factory()->create([
            'zone_id' => $zone->id,
            'recipe_revision_id' => $revision->id,
            'status' => GrowCycleStatus::RUNNING,
        ]);

        $snapshotPhase = GrowCyclePhase::factory()->create([
            'grow_cycle_id' => $cycle->id,
            'recipe_revision_phase_id' => $phase->id,
            'phase_index' => 0,
            'name' => 'Test Phase',
            'ph_target' => 6.0,
            'ph_min' => 5.8,
            'ph_max' => 6.2,
        ]);

        $cycle->update(['current_phase_id' => $snapshotPhase->id]);

        // Создаем override для pH (используем точечную нотацию для вложенных параметров)
        GrowCycleOverride::factory()->create([
            'grow_cycle_id' => $cycle->id,
            'parameter' => 'ph.target',
            'value' => '6.5',
            'value_type' => 'decimal',
            'is_active' => true,
            'applies_from' => now()->subDay(),
            'applies_until' => null,
        ]);

        $result = $this->service->getEffectiveTargets($cycle->id);

        // Проверяем, что override применен
        $this->assertEquals(6.5, $result['targets']['ph']['target']);
        // min и max остаются из фазы
        $this->assertEquals(5.8, $result['targets']['ph']['min']);
        $this->assertEquals(6.2, $result['targets']['ph']['max']);
    }

    #[Test]
    public function it_returns_batch_results_for_multiple_cycles()
    {
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
        ]);

        $snapshotPhase2 = GrowCyclePhase::factory()->create([
            'grow_cycle_id' => $cycle2->id,
            'recipe_revision_phase_id' => $phase->id,
            'phase_index' => 0,
            'name' => 'Test Phase',
            'ph_target' => 6.0,
        ]);

        $cycle1->update(['current_phase_id' => $snapshotPhase1->id]);
        $cycle2->update(['current_phase_id' => $snapshotPhase2->id]);

        $results = $this->service->getEffectiveTargetsBatch([$cycle1->id, $cycle2->id]);

        $this->assertCount(2, $results);
        $this->assertArrayHasKey($cycle1->id, $results);
        $this->assertArrayHasKey($cycle2->id, $results);
        $this->assertArrayHasKey('targets', $results[$cycle1->id]);
        $this->assertArrayHasKey('targets', $results[$cycle2->id]);
    }

    #[Test]
    public function it_handles_missing_current_phase_gracefully()
    {
        $zone = Zone::factory()->create();
        $recipe = Recipe::factory()->create();
        $revision = RecipeRevision::factory()->create([
            'recipe_id' => $recipe->id,
            'status' => 'PUBLISHED',
        ]);

        $cycle = GrowCycle::factory()->create([
            'zone_id' => $zone->id,
            'recipe_revision_id' => $revision->id,
            'status' => GrowCycleStatus::RUNNING,
            'current_phase_id' => null,
        ]);

        $this->expectException(\RuntimeException::class);
        $this->expectExceptionMessage("Grow cycle {$cycle->id} has no current phase");

        $this->service->getEffectiveTargets($cycle->id);
    }

    #[Test]
    public function it_includes_irrigation_targets_in_response()
    {
        $zone = Zone::factory()->create();
        $recipe = Recipe::factory()->create();
        $revision = RecipeRevision::factory()->create([
            'recipe_id' => $recipe->id,
            'status' => 'PUBLISHED',
        ]);

        $phase = RecipeRevisionPhase::factory()->create([
            'recipe_revision_id' => $revision->id,
            'phase_index' => 0,
            'name' => 'Test Phase',
            'irrigation_mode' => 'SUBSTRATE',
            'irrigation_interval_sec' => 3600,
            'irrigation_duration_sec' => 300,
        ]);

        $cycle = GrowCycle::factory()->create([
            'zone_id' => $zone->id,
            'recipe_revision_id' => $revision->id,
            'status' => GrowCycleStatus::RUNNING,
        ]);

        $snapshotPhase = GrowCyclePhase::factory()->create([
            'grow_cycle_id' => $cycle->id,
            'recipe_revision_phase_id' => $phase->id,
            'phase_index' => 0,
            'name' => 'Test Phase',
            'irrigation_mode' => 'SUBSTRATE',
            'irrigation_interval_sec' => 3600,
            'irrigation_duration_sec' => 300,
        ]);

        $cycle->update(['current_phase_id' => $snapshotPhase->id]);

        $result = $this->service->getEffectiveTargets($cycle->id);

        $this->assertArrayHasKey('irrigation', $result['targets']);
        $this->assertEquals('SUBSTRATE', $result['targets']['irrigation']['mode']);
        $this->assertEquals(3600, $result['targets']['irrigation']['interval_sec']);
        $this->assertEquals(300, $result['targets']['irrigation']['duration_sec']);
    }
}
