<?php

namespace Tests\Unit;

use App\Enums\GrowCycleStatus;
use App\Jobs\RunSimulationReportJob;
use App\Models\GrowCycle;
use App\Models\GrowCyclePhase;
use App\Models\Plant;
use App\Models\Recipe;
use App\Models\RecipeRevision;
use App\Models\RecipeRevisionPhase;
use App\Models\SimulationReport;
use App\Models\User;
use App\Models\Zone;
use App\Models\ZoneSimulation;
use App\Services\GrowCycleService;
use App\Services\SimulationOrchestratorService;
use Tests\RefreshDatabase;
use Tests\TestCase;

class RunSimulationReportJobTest extends TestCase
{
    use RefreshDatabase;

    public function test_live_simulation_report_does_not_harvest_cycle(): void
    {
        User::factory()->create();

        $zone = Zone::factory()->create(['status' => 'online']);
        $plant = Plant::factory()->create();
        $recipe = Recipe::factory()->create();
        $revision = RecipeRevision::factory()->published()->create([
            'recipe_id' => $recipe->id,
        ]);
        $revisionPhase = RecipeRevisionPhase::factory()->create([
            'recipe_revision_id' => $revision->id,
            'phase_index' => 0,
        ]);

        $growCycle = GrowCycle::factory()->running()->create([
            'zone_id' => $zone->id,
            'greenhouse_id' => $zone->greenhouse_id,
            'plant_id' => $plant->id,
            'recipe_id' => $recipe->id,
            'recipe_revision_id' => $revision->id,
        ]);

        $growPhase = GrowCyclePhase::factory()->create([
            'grow_cycle_id' => $growCycle->id,
            'recipe_revision_phase_id' => $revisionPhase->id,
            'phase_index' => 0,
            'name' => 'Phase 1',
            'started_at' => now(),
        ]);
        $growCycle->update(['current_phase_id' => $growPhase->id]);

        $simulation = ZoneSimulation::factory()->create([
            'zone_id' => $zone->id,
            'status' => 'running',
            'scenario' => [
                'recipe_id' => $recipe->id,
                'simulation' => [
                    'mode' => 'live',
                    'real_duration_minutes' => 5,
                    'sim_zone_id' => $zone->id,
                    'sim_grow_cycle_id' => $growCycle->id,
                ],
            ],
        ]);

        SimulationReport::create([
            'simulation_id' => $simulation->id,
            'zone_id' => $zone->id,
            'status' => 'running',
            'started_at' => now(),
            'summary_json' => [],
            'phases_json' => [[
                'phase_id' => $growPhase->id,
                'phase_index' => 0,
                'name' => $growPhase->name,
                'started_at' => now()->toIso8601String(),
                'completed_at' => null,
                'status' => 'running',
            ]],
        ]);

        $job = new RunSimulationReportJob($simulation->id);
        $job->handle(app(GrowCycleService::class), app(SimulationOrchestratorService::class));

        $this->assertSame(GrowCycleStatus::RUNNING, $growCycle->refresh()->status);
    }
}
