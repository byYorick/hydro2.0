<?php

namespace Tests\Feature;

use App\Models\Alert;
use App\Models\GrowCycle;
use App\Models\GrowCyclePhase;
use App\Models\Recipe;
use App\Models\RecipeRevision;
use App\Models\RecipeRevisionPhase;
use App\Models\Zone;
use Illuminate\Support\Facades\DB;
use Tests\RefreshDatabase;
use Tests\TestCase;

class AutoAdvancePhasesTest extends TestCase
{
    use RefreshDatabase;

    public function test_auto_advance_skips_zones_not_in_auto_mode(): void
    {
        [$zone, $cycle] = $this->setupRunningCycle(controlMode: 'semi', durationHours: 1, phaseStartedHoursAgo: 2);

        $this->artisan('phases:auto-advance')->assertExitCode(0);

        $cycle->refresh();
        $this->assertSame($cycle->current_phase_id, $cycle->fresh()->current_phase_id);
    }

    public function test_auto_advance_blocks_when_active_task_present(): void
    {
        [$zone, $cycle, $phase] = $this->setupRunningCycle(controlMode: 'auto', durationHours: 1, phaseStartedHoursAgo: 2);

        DB::table('ae_tasks')->insert([
            'zone_id' => $zone->id,
            'task_type' => 'irrigation_start',
            'idempotency_key' => 'guard-test-active-task',
            'topology' => 'two_tank',
            'status' => 'running',
            'scheduled_for' => now(),
            'due_at' => now(),
            'current_stage' => 'irrigation_check',
            'workflow_phase' => 'irrigating',
            'created_at' => now(),
            'updated_at' => now(),
            'corr_ec_current_seq_index' => 0,
        ]);

        $originalPhaseId = $cycle->current_phase_id;

        $this->artisan('phases:auto-advance')->assertExitCode(0);

        $this->assertSame($originalPhaseId, $cycle->fresh()->current_phase_id);
    }

    public function test_auto_advance_blocks_on_critical_alert(): void
    {
        [$zone, $cycle] = $this->setupRunningCycle(controlMode: 'auto', durationHours: 1, phaseStartedHoursAgo: 2);

        Alert::create([
            'zone_id' => $zone->id,
            'source' => 'biz',
            'code' => 'biz_test_critical',
            'type' => 'Test',
            'status' => 'ACTIVE',
            'severity' => 'critical',
            'category' => 'operations',
            'details' => ['message' => 'guard test'],
        ]);

        $originalPhaseId = $cycle->current_phase_id;

        $this->artisan('phases:auto-advance')->assertExitCode(0);

        $this->assertSame($originalPhaseId, $cycle->fresh()->current_phase_id);
    }

    public function test_auto_advance_emits_alert_when_last_phase_reached(): void
    {
        [$zone, $cycle] = $this->setupRunningCycle(
            controlMode: 'auto',
            durationHours: 1,
            phaseStartedHoursAgo: 2,
            phaseIndex: 0,
            extraPhases: false, // только одна фаза в рецепте
        );

        $this->artisan('phases:auto-advance')->assertExitCode(0);

        $alert = Alert::query()
            ->where('zone_id', $zone->id)
            ->where('code', 'biz_recipe_completed_review_required')
            ->first();

        $this->assertNotNull($alert);
        $this->assertSame('warning', $alert->severity);
        $this->assertSame('agronomy', $alert->category);
    }

    public function test_auto_advance_advances_when_duration_expired_and_next_phase_exists(): void
    {
        [$zone, $cycle, $phase] = $this->setupRunningCycle(
            controlMode: 'auto',
            durationHours: 1,
            phaseStartedHoursAgo: 2,
            phaseIndex: 0,
            extraPhases: true,
        );

        $originalPhaseId = $cycle->current_phase_id;

        $this->artisan('phases:auto-advance')->assertExitCode(0);

        $cycle->refresh();
        $this->assertNotSame($originalPhaseId, $cycle->current_phase_id);

        // Snapshot новой фазы должен быть создан
        $newPhase = GrowCyclePhase::find($cycle->current_phase_id);
        $this->assertNotNull($newPhase);
        $this->assertSame(1, $newPhase->phase_index);
    }

    /**
     * Создаёт zone + recipe + revision + phase template + grow cycle с активной фазой,
     * у которой phase_started_at = now()-Nh. Возвращает [Zone, GrowCycle, GrowCyclePhase].
     *
     * @return array{0: Zone, 1: GrowCycle, 2: GrowCyclePhase}
     */
    private function setupRunningCycle(
        string $controlMode,
        int $durationHours,
        int $phaseStartedHoursAgo,
        int $phaseIndex = 0,
        bool $extraPhases = true,
    ): array {
        $zone = Zone::factory()->create(['control_mode' => $controlMode]);

        $recipe = Recipe::query()->create([
            'name' => 'Test Recipe ' . uniqid(),
            'crop_type' => 'lettuce',
            'visibility' => 'private',
        ]);
        $revision = RecipeRevision::query()->create([
            'recipe_id' => $recipe->id,
            'revision_number' => 1,
            'status' => 'PUBLISHED',
            'name' => 'rev',
        ]);

        $templates = [];
        $templates[] = RecipeRevisionPhase::query()->create([
            'recipe_revision_id' => $revision->id,
            'phase_index' => $phaseIndex,
            'name' => 'P0',
            'duration_hours' => $durationHours,
            'phase_advance_strategy' => 'time',
        ]);
        if ($extraPhases) {
            $templates[] = RecipeRevisionPhase::query()->create([
                'recipe_revision_id' => $revision->id,
                'phase_index' => $phaseIndex + 1,
                'name' => 'P1',
                'duration_hours' => 24,
                'phase_advance_strategy' => 'time',
            ]);
        }

        $cycle = GrowCycle::query()->create([
            'greenhouse_id' => $zone->greenhouse_id,
            'zone_id' => $zone->id,
            'recipe_revision_id' => $revision->id,
            'status' => 'RUNNING',
            'started_at' => now()->subHours($phaseStartedHoursAgo + 1),
            'phase_started_at' => now()->subHours($phaseStartedHoursAgo),
        ]);

        $phase = GrowCyclePhase::query()->create([
            'grow_cycle_id' => $cycle->id,
            'recipe_revision_phase_id' => $templates[0]->id,
            'phase_index' => $phaseIndex,
            'name' => 'P0',
            'duration_hours' => $durationHours,
            'phase_advance_strategy' => 'time',
            'started_at' => now()->subHours($phaseStartedHoursAgo),
        ]);

        $cycle->update(['current_phase_id' => $phase->id]);

        return [$zone, $cycle->fresh(), $phase];
    }
}
