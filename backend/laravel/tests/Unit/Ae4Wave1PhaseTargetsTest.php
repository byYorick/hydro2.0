<?php

declare(strict_types=1);

namespace Tests\Unit;

use App\Models\GrowCycle;
use App\Models\RecipeRevision;
use App\Models\RecipeRevisionPhase;
use App\Services\GrowCycle\Support\PhaseSnapshotCreator;
use App\Support\Recipes\RecipePhaseRules;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Tests\TestCase;

class Ae4Wave1PhaseTargetsTest extends TestCase
{
    use RefreshDatabase;

    public function test_phase_snapshot_copies_ae4_water_demand_columns(): void
    {
        $revision = RecipeRevision::factory()->create();
        $template = RecipeRevisionPhase::factory()->create([
            'recipe_revision_id' => $revision->id,
            'irrigation_interval_sec' => 1800,
            'irrigation_duration_sec' => 45,
            'soil_moisture_min' => 35.5,
            'soil_moisture_max' => 55.0,
            'vpd_min' => 0.800,
            'vpd_max' => 1.400,
            'light_integral_per_shot' => 12000.5,
        ]);
        $cycle = GrowCycle::factory()->create([
            'recipe_revision_id' => $revision->id,
        ]);

        $snapshot = (new PhaseSnapshotCreator)->create($cycle, $template);

        $this->assertSame(35.5, (float) $snapshot->soil_moisture_min);
        $this->assertSame(55.0, (float) $snapshot->soil_moisture_max);
        $this->assertSame(0.8, (float) $snapshot->vpd_min);
        $this->assertSame(1.4, (float) $snapshot->vpd_max);
        $this->assertSame(12000.5, (float) $snapshot->light_integral_per_shot);
        $this->assertSame(1800, $snapshot->irrigation_interval_sec);
    }

    public function test_recipe_phase_rules_accept_ae4_columns(): void
    {
        $rules = RecipePhaseRules::store();
        $this->assertArrayHasKey('soil_moisture_min', $rules);
        $this->assertArrayHasKey('soil_moisture_max', $rules);
        $this->assertArrayHasKey('vpd_min', $rules);
        $this->assertArrayHasKey('vpd_max', $rules);
        $this->assertArrayHasKey('light_integral_per_shot', $rules);

        $validator = validator([
            'name' => 'VEG',
            'ph_target' => 5.8,
            'ph_min' => 5.6,
            'ph_max' => 6.0,
            'ec_target' => 1.4,
            'ec_min' => 1.2,
            'ec_max' => 1.6,
            'soil_moisture_min' => 40,
            'soil_moisture_max' => 60,
            'vpd_min' => 0.5,
            'vpd_max' => 1.2,
            'light_integral_per_shot' => 9000,
        ], $rules);

        $this->assertTrue($validator->passes(), (string) $validator->errors());
    }
}
