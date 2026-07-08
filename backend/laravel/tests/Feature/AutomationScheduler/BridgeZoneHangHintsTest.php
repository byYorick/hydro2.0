<?php

namespace Tests\Feature\AutomationScheduler;

use App\Models\Alert;
use App\Models\Zone;
use App\Services\AutomationScheduler\ZoneHangHintsQuery;
use Illuminate\Support\Facades\DB;
use Tests\RefreshDatabase;
use Tests\TestCase;

class BridgeZoneHangHintsTest extends TestCase
{
    use RefreshDatabase;

    public function test_bridge_creates_alert_for_active_waiting_command_hint(): void
    {
        $zone = Zone::factory()->create();
        $staleAt = now()->subMinutes(5);

        DB::table('ae_tasks')->insert([
            'zone_id' => $zone->id,
            'task_type' => 'cycle_start',
            'status' => 'waiting_command',
            'idempotency_key' => 'bridge-hang-hint-'.uniqid(),
            'topology' => 'two_tank_drip_substrate_trays',
            'current_stage' => 'clean_fill_check',
            'workflow_phase' => 'tank_filling',
            'control_mode_snapshot' => 'auto',
            'scheduled_for' => $staleAt,
            'due_at' => $staleAt,
            'stage_entered_at' => $staleAt,
            'created_at' => $staleAt,
            'updated_at' => $staleAt,
        ]);

        $this->artisan('automation:bridge-hang-hints')->assertSuccessful();

        $alert = Alert::query()
            ->where('zone_id', $zone->id)
            ->where('code', 'biz_zone_hang_hint_waiting_command_stuck')
            ->where('status', 'ACTIVE')
            ->first();

        $this->assertNotNull($alert);
        $this->assertSame('infra', $alert->source);
        $this->assertSame(
            sprintf('hang_hint|%s|zone:%d', ZoneHangHintsQuery::HINT_WAITING_COMMAND_STUCK, $zone->id),
            $alert->details['dedupe_key'] ?? null,
        );
        $this->assertSame('cron:automation:bridge-hang-hints', $alert->details['component'] ?? null);
    }

    public function test_bridge_uses_existing_alert_code_for_stage_deadline_exceeded(): void
    {
        $zone = Zone::factory()->create();
        $startedAt = now()->subHour();

        DB::table('ae_tasks')->insert([
            'zone_id' => $zone->id,
            'task_type' => 'cycle_start',
            'status' => 'running',
            'idempotency_key' => 'bridge-deadline-hint-'.uniqid(),
            'topology' => 'two_tank_drip_substrate_trays',
            'current_stage' => 'clean_fill_check',
            'workflow_phase' => 'tank_filling',
            'control_mode_snapshot' => 'auto',
            'scheduled_for' => $startedAt,
            'due_at' => $startedAt,
            'stage_entered_at' => $startedAt,
            'stage_deadline_at' => now()->subMinute(),
            'created_at' => $startedAt,
            'updated_at' => $startedAt,
        ]);

        $this->artisan('automation:bridge-hang-hints')->assertSuccessful();

        $this->assertDatabaseHas('alerts', [
            'zone_id' => $zone->id,
            'code' => 'ae3_stage_deadline_exceeded',
            'source' => 'infra',
            'status' => 'ACTIVE',
        ]);
    }

    public function test_bridge_resolves_alert_when_hint_clears(): void
    {
        $zone = Zone::factory()->create();
        $staleAt = now()->subMinutes(5);

        DB::table('ae_tasks')->insert([
            'zone_id' => $zone->id,
            'task_type' => 'cycle_start',
            'status' => 'waiting_command',
            'idempotency_key' => 'bridge-resolve-hint-'.uniqid(),
            'topology' => 'two_tank_drip_substrate_trays',
            'current_stage' => 'clean_fill_check',
            'workflow_phase' => 'tank_filling',
            'control_mode_snapshot' => 'auto',
            'scheduled_for' => $staleAt,
            'due_at' => $staleAt,
            'stage_entered_at' => $staleAt,
            'created_at' => $staleAt,
            'updated_at' => $staleAt,
        ]);

        $this->artisan('automation:bridge-hang-hints')->assertSuccessful();

        DB::table('ae_tasks')
            ->where('zone_id', $zone->id)
            ->update([
                'status' => 'completed',
                'updated_at' => now(),
            ]);

        $this->artisan('automation:bridge-hang-hints')->assertSuccessful();

        $this->assertDatabaseHas('alerts', [
            'zone_id' => $zone->id,
            'code' => 'biz_zone_hang_hint_waiting_command_stuck',
            'status' => 'RESOLVED',
        ]);
    }
}
