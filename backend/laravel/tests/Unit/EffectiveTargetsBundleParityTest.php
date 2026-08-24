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
        $this->assertArrayNotHasKey('ph_target', $snapshotPhase);
        $this->assertArrayNotHasKey('ph_min', $snapshotPhase);
        $this->assertArrayNotHasKey('ph_max', $snapshotPhase);
        $this->assertArrayNotHasKey('ec_target', $snapshotPhase);
        $this->assertArrayNotHasKey('ec_min', $snapshotPhase);
        $this->assertArrayNotHasKey('ec_max', $snapshotPhase);
        $this->assertSame(5.80, (float) data_get($effective, 'targets.ph.target'));
        $this->assertSame(1.40, (float) data_get($effective, 'targets.ec.target'));
    }

    #[Test]
    public function chemical_ph_ec_match_sql_current_phase_after_phase_switch(): void
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
            'name' => 'VEG',
            'ph_target' => 5.80,
            'ph_min' => 5.60,
            'ph_max' => 6.00,
            'ec_target' => 1.40,
            'ec_min' => 1.20,
            'ec_max' => 1.60,
        ]);
        RecipeRevisionPhase::factory()->create([
            'recipe_revision_id' => $revision->id,
            'phase_index' => 1,
            'name' => 'FLOWER',
            'ph_target' => 6.20,
            'ph_min' => 6.00,
            'ph_max' => 6.40,
            'ec_target' => 2.00,
            'ec_min' => 1.80,
            'ec_max' => 2.20,
        ]);

        $cycle = app(GrowCycleService::class)->createCycle($zone, $revision, (int) $plant->id);
        $user = \App\Models\User::factory()->create(['role' => 'agronomist']);
        $advanced = app(GrowCycleService::class)->advancePhase($cycle->fresh(), (int) $user->id);
        $current = $advanced->fresh()->currentPhase;
        $this->assertNotNull($current);
        $this->assertSame('FLOWER', $current->name);

        $effective = app(EffectiveTargetsService::class)->getEffectiveTargets((int) $advanced->id);

        $this->assertSame((float) $current->ph_target, (float) data_get($effective, 'targets.ph.target'));
        $this->assertSame((float) $current->ph_min, (float) data_get($effective, 'targets.ph.min'));
        $this->assertSame((float) $current->ph_max, (float) data_get($effective, 'targets.ph.max'));
        $this->assertSame((float) $current->ec_target, (float) data_get($effective, 'targets.ec.target'));
        $this->assertSame((float) $current->ec_min, (float) data_get($effective, 'targets.ec.min'));
        $this->assertSame((float) $current->ec_max, (float) data_get($effective, 'targets.ec.max'));
        $this->assertNotSame(
            5.80,
            (float) data_get($effective, 'targets.ph.target'),
        );
    }

    #[Test]
    public function irrigation_and_lighting_execution_match_compiled_bundle_logic_profile_path(): void
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
            'irrigation_mode' => 'SUBSTRATE',
            'irrigation_interval_sec' => 3600,
            'irrigation_duration_sec' => 300,
            'lighting_photoperiod_hours' => 16,
            'lighting_start_time' => '06:00:00',
        ]);

        $cycle = app(GrowCycleService::class)->createCycle($zone, $revision, (int) $plant->id);

        $payload = $documents->getPayload(
            AutomationConfigRegistry::NAMESPACE_ZONE_LOGIC_PROFILE,
            AutomationConfigRegistry::SCOPE_ZONE,
            (int) $zone->id,
            true
        );
        $profiles = is_array($payload['profiles'] ?? null) ? $payload['profiles'] : [];
        $profiles['working'] = [
            'mode' => 'working',
            'is_active' => true,
            'subsystems' => [
                'irrigation' => [
                    'enabled' => true,
                    'execution' => [
                        'interval_minutes' => 15,
                        'duration_seconds' => 40,
                    ],
                ],
                'lighting' => [
                    'enabled' => true,
                    'execution' => [
                        'photoperiod' => ['hours_on' => 12],
                        'start_time' => '07:30',
                    ],
                ],
            ],
        ];
        $documents->upsertDocument(
            AutomationConfigRegistry::NAMESPACE_ZONE_LOGIC_PROFILE,
            AutomationConfigRegistry::SCOPE_ZONE,
            (int) $zone->id,
            [
                'active_mode' => 'working',
                'profiles' => $profiles,
            ],
        );

        $bundle = AutomationEffectiveBundle::query()
            ->where('scope_type', AutomationConfigRegistry::SCOPE_GROW_CYCLE)
            ->where('scope_id', $cycle->id)
            ->firstOrFail();

        $effective = app(EffectiveTargetsService::class)->getEffectiveTargets((int) $cycle->id);
        $irrigationExecution = data_get($bundle->config, 'zone.logic_profile.active_profile.subsystems.irrigation.execution');
        $lightingExecution = data_get($bundle->config, 'zone.logic_profile.active_profile.subsystems.lighting.execution');

        $this->assertIsArray($irrigationExecution);
        $this->assertIsArray($lightingExecution);
        $this->assertSame(
            (int) $irrigationExecution['interval_minutes'] * 60,
            (int) data_get($effective, 'targets.irrigation.interval_sec'),
        );
        $this->assertSame(
            (int) $irrigationExecution['duration_seconds'],
            (int) data_get($effective, 'targets.irrigation.duration_sec'),
        );
        $this->assertSame(16.0, (float) data_get($effective, 'targets.lighting.photoperiod_hours'));
        $this->assertSame('06:00:00', (string) data_get($effective, 'targets.lighting.start_time'));
        $this->assertSame(12.0, (float) data_get($lightingExecution, 'photoperiod.hours_on'));
    }
}
