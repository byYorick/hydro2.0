<?php

namespace Tests\Unit;

use App\Models\AutomationEffectiveBundle;
use App\Models\Plant;
use App\Models\Recipe;
use App\Models\RecipeRevision;
use App\Models\RecipeRevisionPhase;
use App\Models\Zone;
use App\Services\AutomationConfigCompiler;
use App\Services\AutomationConfigDocumentService;
use App\Services\AutomationConfigRegistry;
use App\Services\EffectiveTargetsService;
use App\Services\GrowCycleService;
use PHPUnit\Framework\Attributes\Test;
use Tests\RefreshDatabase;
use Tests\TestCase;

class EffectiveTargetsBundleParityTest extends TestCase
{
    use RefreshDatabase;

    #[Test]
    public function chemical_ph_ec_from_effective_targets_match_compiled_grow_cycle_bundle(): void
    {
        $documents = app(AutomationConfigDocumentService::class);
        $documents->ensureSystemDefaults();

        $zone = Zone::factory()->create();
        $documents->ensureZoneDefaults((int) $zone->id);

        $plant = Plant::factory()->create();
        $recipe = Recipe::factory()->create();
        $revision = RecipeRevision::factory()->create([
            'recipe_id' => $recipe->id,
            'status' => 'PUBLISHED',
        ]);
        RecipeRevisionPhase::factory()->create([
            'recipe_revision_id' => $revision->id,
            'phase_index' => 0,
            'name' => 'Parity Phase',
            'ph_target' => 5.80,
            'ph_min' => 5.60,
            'ph_max' => 6.00,
            'ec_target' => 1.40,
            'ec_min' => 1.20,
            'ec_max' => 1.60,
        ]);

        $cycle = app(GrowCycleService::class)->createCycle($zone, $revision, (int) $plant->id);
        app(GrowCycleService::class)->syncCycleConfigDocuments($cycle);
        app(AutomationConfigCompiler::class)->compileGrowCycleBundle((int) $cycle->id);

        $bundle = AutomationEffectiveBundle::query()
            ->where('scope_type', AutomationConfigRegistry::SCOPE_GROW_CYCLE)
            ->where('scope_id', $cycle->id)
            ->firstOrFail();

        $effective = app(EffectiveTargetsService::class)->getEffectiveTargets((int) $cycle->id);
        $snapshotPhase = data_get($bundle->config, 'cycle.start_snapshot.phase');

        $this->assertIsArray($snapshotPhase);
        $this->assertSame(
            $this->chemicalPhEc($effective['targets'] ?? []),
            $this->chemicalPhEcFromSnapshot($snapshotPhase),
        );
    }

    /**
     * @param  array<string, mixed>  $targets
     * @return array{ph: array{target: float, min: float, max: float}, ec: array{target: float, min: float, max: float}}
     */
    private function chemicalPhEc(array $targets): array
    {
        return [
            'ph' => [
                'target' => (float) data_get($targets, 'ph.target'),
                'min' => (float) data_get($targets, 'ph.min'),
                'max' => (float) data_get($targets, 'ph.max'),
            ],
            'ec' => [
                'target' => (float) data_get($targets, 'ec.target'),
                'min' => (float) data_get($targets, 'ec.min'),
                'max' => (float) data_get($targets, 'ec.max'),
            ],
        ];
    }

    /**
     * @param  array<string, mixed>  $snapshotPhase
     * @return array{ph: array{target: float, min: float, max: float}, ec: array{target: float, min: float, max: float}}
     */
    private function chemicalPhEcFromSnapshot(array $snapshotPhase): array
    {
        return [
            'ph' => [
                'target' => (float) ($snapshotPhase['ph_target'] ?? 0),
                'min' => (float) ($snapshotPhase['ph_min'] ?? 0),
                'max' => (float) ($snapshotPhase['ph_max'] ?? 0),
            ],
            'ec' => [
                'target' => (float) ($snapshotPhase['ec_target'] ?? 0),
                'min' => (float) ($snapshotPhase['ec_min'] ?? 0),
                'max' => (float) ($snapshotPhase['ec_max'] ?? 0),
            ],
        ];
    }
}
