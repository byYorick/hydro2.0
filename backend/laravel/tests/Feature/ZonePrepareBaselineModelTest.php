<?php

namespace Tests\Feature;

use App\Models\GrowCycle;
use App\Models\Zone;
use App\Models\ZonePrepareBaseline;
use Illuminate\Support\Carbon;
use Tests\RefreshDatabase;
use Tests\TestCase;

class ZonePrepareBaselineModelTest extends TestCase
{
    use RefreshDatabase;

    public function test_model_persists_baseline_payload_and_casts(): void
    {
        $zone = Zone::factory()->create();
        $growCycle = GrowCycle::factory()->create(['zone_id' => $zone->id]);

        $baseline = ZonePrepareBaseline::query()->create([
            'zone_id' => $zone->id,
            'grow_cycle_id' => $growCycle->id,
            'ae_task_id' => null,
            'water_ec' => 0.35,
            'water_ph' => 7.1,
            'target_ec' => 1.8,
            'nutrient_ec_budget' => 1.45,
            'ratios_json' => [
                'calcium' => 30.0,
                'magnesium' => 20.0,
                'npk' => 40.0,
                'micro' => 10.0,
            ],
            'component_targets_json' => [
                'T_ca' => 0.785,
                'T_full' => 1.8,
            ],
            'captured_at' => Carbon::parse('2026-07-22T08:00:00Z'),
            'source' => 'ae3',
        ]);

        $fresh = ZonePrepareBaseline::query()->findOrFail($baseline->id);

        $this->assertSame($zone->id, $fresh->zone_id);
        $this->assertSame($growCycle->id, $fresh->grow_cycle_id);
        $this->assertEqualsWithDelta(0.35, (float) $fresh->water_ec, 1e-6);
        $this->assertEqualsWithDelta(1.45, (float) $fresh->nutrient_ec_budget, 1e-6);
        $this->assertEqualsWithDelta(30.0, (float) $fresh->ratios_json['calcium'], 1e-6);
        $this->assertEqualsWithDelta(0.785, (float) $fresh->component_targets_json['T_ca'], 1e-6);
        $this->assertSame('ae3', $fresh->source);
        $this->assertTrue($fresh->zone()->exists());
        $this->assertTrue($fresh->growCycle()->exists());
    }
}
