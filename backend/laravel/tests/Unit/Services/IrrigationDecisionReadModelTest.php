<?php

namespace Tests\Unit\Services;

use App\Models\Zone;
use App\Services\IrrigationDecisionReadModel;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Illuminate\Support\Facades\DB;
use Tests\TestCase;

class IrrigationDecisionReadModelTest extends TestCase
{
    use RefreshDatabase;

    private function task(Zone $zone, array $overrides = []): int
    {
        return DB::table('ae_tasks')->insertGetId(array_merge([
            'zone_id' => $zone->id,
            'task_type' => 'irrigation_start',
            'status' => 'completed',
            'idempotency_key' => (string) \Illuminate\Support\Str::uuid(),
            'topology' => 'two_tank_drip_substrate_trays',
            'current_stage' => 'completed_skip',
            'workflow_phase' => 'ready',
            'control_mode_snapshot' => 'auto',
            'scheduled_for' => now(), 'due_at' => now(),
            'created_at' => now(), 'updated_at' => now(),
            'irrigation_decision_strategy' => 'smart_soil_v1',
            'irrigation_decision_outcome' => 'skip',
            'irrigation_decision_reason_code' => 'smart_soil_within_band',
            'irrigation_decision_degraded' => false,
            'irrigation_decision_config' => json_encode(['hysteresis_pct' => 2, 'min_samples' => 3]),
        ], $overrides));
    }

    private function event(Zone $zone, int $taskId, array $overrides = []): void
    {
        DB::table('zone_events')->insert([
            'zone_id' => $zone->id, 'type' => 'IRRIGATION_DECISION_EVALUATED',
            'created_at' => now(),
            'payload_json' => json_encode(array_merge([
                'task_id' => $taskId, 'outcome' => 'skip', 'reason_code' => 'smart_soil_within_band',
                'details' => ['zone_average_pct' => 45, 'run_below_pct' => 38],
            ], $overrides)),
        ]);
    }

    public function test_completed_skip_keeps_its_observations_and_frozen_config(): void
    {
        $zone = Zone::factory()->create();
        $id = $this->task($zone);
        $this->event($zone, $id);
        $result = app(IrrigationDecisionReadModel::class)->forZone($zone->id);

        $this->assertSame($id, $result['task_id']);
        $this->assertSame('skip', $result['outcome']);
        $this->assertSame(45, $result['details']['zone_average_pct']);
        $this->assertSame(2, $result['config']['hysteresis_pct']);
        $this->assertFalse($result['degraded']);
        $this->assertStringEndsWith('+00:00', $result['evaluated_at']);
    }

    public function test_new_pending_task_never_inherits_previous_task_decision(): void
    {
        $zone = Zone::factory()->create();
        $old = $this->task($zone);
        $this->event($zone, $old);
        $pending = $this->task($zone, [
            'status' => 'pending', 'current_stage' => 'await_ready',
            'irrigation_decision_outcome' => null, 'irrigation_decision_reason_code' => null,
        ]);

        $result = app(IrrigationDecisionReadModel::class)->forZone($zone->id);
        $this->assertSame($pending, $result['task_id']);
        $this->assertNull($result['outcome']);
        $this->assertNull($result['details']);
        $this->assertNull($result['evaluated_at']);
    }

    public function test_event_must_match_zone_task_outcome_and_reason(): void
    {
        $zone = Zone::factory()->create();
        $other = Zone::factory()->create();
        $id = $this->task($zone);
        $this->event($zone, $id + 100);
        $this->event($other, $id);
        $this->event($zone, $id, ['outcome' => 'run']);
        $this->event($zone, $id, ['reason_code' => 'smart_soil_above_max']);

        $this->assertNull(app(IrrigationDecisionReadModel::class)->forZone($zone->id)['details']);
        $this->event($zone, $id);
        $this->assertSame(45, app(IrrigationDecisionReadModel::class)->forZone($zone->id)['details']['zone_average_pct']);
    }

    public function test_no_irrigation_task_is_explicitly_empty(): void
    {
        $zone = Zone::factory()->create();
        $this->task($zone, ['task_type' => 'cycle_start']);
        $this->assertNull(app(IrrigationDecisionReadModel::class)->forZone($zone->id));
    }
}
