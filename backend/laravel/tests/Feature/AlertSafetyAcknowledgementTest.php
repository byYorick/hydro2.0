<?php

namespace Tests\Feature;

use App\Exceptions\ManualAlertResolveRefusedException;
use App\Models\Alert;
use App\Models\User;
use App\Models\Zone;
use App\Services\AlertService;
use App\Services\SafetyCriticalAlertCodes;
use Illuminate\Support\Facades\DB;
use Tests\RefreshDatabase;
use Tests\TestCase;

class AlertSafetyAcknowledgementTest extends TestCase
{
    use RefreshDatabase;

    public function test_acknowledge_keeps_active_status_and_sets_acknowledgement_fields(): void
    {
        $user = User::factory()->create(['role' => 'operator']);
        $zone = Zone::factory()->create();
        $alert = Alert::factory()->create([
            'zone_id' => $zone->id,
            'code' => 'biz_dry_run',
            'status' => 'ACTIVE',
            'severity' => 'critical',
        ]);

        $response = $this->actingAs($user)
            ->withHeader('Authorization', 'Bearer '.$user->createToken('test')->plainTextToken)
            ->patchJson("/api/alerts/{$alert->id}/ack");

        $response->assertOk()
            ->assertJsonPath('data.status', 'ACTIVE')
            ->assertJsonPath('data.acknowledged_by', $user->id)
            ->assertJsonPath('data.code', 'biz_dry_run');
        $this->assertNotNull($response->json('data.acknowledged_at'));

        $alert->refresh();
        $this->assertSame('ACTIVE', $alert->status);
        $this->assertNull($alert->resolved_at);
        $this->assertNotNull($alert->acknowledged_at);
        $this->assertSame($user->id, $alert->acknowledged_by);
        $this->assertDatabaseHas('zone_events', [
            'zone_id' => $zone->id,
            'type' => 'ALERT_ACKNOWLEDGED',
            'entity_type' => 'alert',
            'entity_id' => (string) $alert->id,
        ]);
    }

    public function test_acknowledged_safety_alert_stays_visible_to_ae3_active_gate(): void
    {
        $user = User::factory()->create(['role' => 'engineer']);
        $zone = Zone::factory()->create();
        $alert = Alert::factory()->create([
            'zone_id' => $zone->id,
            'code' => 'biz_node_offline',
            'status' => 'ACTIVE',
            'severity' => 'error',
        ]);

        $this->actingAs($user)
            ->withHeader('Authorization', 'Bearer '.$user->createToken('test')->plainTextToken)
            ->patchJson("/api/alerts/{$alert->id}/ack")
            ->assertOk()
            ->assertJsonPath('data.status', 'ACTIVE');

        // Тот же предикат, что PgZoneAlertRepository.has_active_alert / find_first_active_by_codes.
        $stillBlocking = DB::table('alerts')
            ->where('zone_id', $zone->id)
            ->whereRaw('LOWER(code) = ?', ['biz_node_offline'])
            ->where('status', 'ACTIVE')
            ->exists();

        $this->assertTrue($stillBlocking);
    }

    public function test_manual_resolve_of_active_safety_alert_is_refused_and_audited(): void
    {
        $user = User::factory()->create(['role' => 'operator']);
        $zone = Zone::factory()->create();
        $alert = Alert::factory()->create([
            'zone_id' => $zone->id,
            'code' => 'biz_dry_run',
            'status' => 'ACTIVE',
            'severity' => 'critical',
        ]);

        $response = $this->actingAs($user)
            ->withHeader('Authorization', 'Bearer '.$user->createToken('test')->plainTextToken)
            ->patchJson("/api/alerts/{$alert->id}/resolve");

        $response->assertStatus(409)
            ->assertJsonPath('status', 'error')
            ->assertJsonPath('code', ManualAlertResolveRefusedException::ERROR_CODE);

        $alert->refresh();
        $this->assertSame('ACTIVE', $alert->status);
        $this->assertNull($alert->resolved_at);
        $this->assertDatabaseHas('zone_events', [
            'zone_id' => $zone->id,
            'type' => 'ALERT_MANUAL_RESOLVE_REFUSED',
            'entity_type' => 'alert',
            'entity_id' => (string) $alert->id,
        ]);
    }

    public function test_manual_resolve_of_non_critical_alert_is_allowed(): void
    {
        $user = User::factory()->create(['role' => 'agronomist']);
        $zone = Zone::factory()->create();
        $alert = Alert::factory()->create([
            'zone_id' => $zone->id,
            'code' => 'biz_high_ph',
            'status' => 'ACTIVE',
            'severity' => 'warning',
        ]);

        $response = $this->actingAs($user)
            ->withHeader('Authorization', 'Bearer '.$user->createToken('test')->plainTextToken)
            ->patchJson("/api/alerts/{$alert->id}/resolve");

        $response->assertOk()
            ->assertJsonPath('data.status', 'RESOLVED');

        $alert->refresh();
        $this->assertSame('RESOLVED', $alert->status);
        $this->assertNotNull($alert->resolved_at);
        $this->assertSame('manual', $alert->details['resolved_via'] ?? null);
        $this->assertSame($user->id, $alert->details['resolved_by_user_id'] ?? null);
    }

    public function test_every_safety_critical_code_refuses_manual_resolve_while_active(): void
    {
        $user = User::factory()->create(['role' => 'admin']);
        $zone = Zone::factory()->create();

        foreach (SafetyCriticalAlertCodes::CODES as $code) {
            $alert = Alert::factory()->create([
                'zone_id' => $zone->id,
                'code' => $code,
                'status' => 'ACTIVE',
            ]);

            $this->actingAs($user)
                ->withHeader('Authorization', 'Bearer '.$user->createToken('test')->plainTextToken)
                ->patchJson("/api/alerts/{$alert->id}/resolve")
                ->assertStatus(409)
                ->assertJsonPath('code', ManualAlertResolveRefusedException::ERROR_CODE);

            $this->assertSame('ACTIVE', $alert->fresh()->status);
        }
    }

    public function test_automatic_resolve_of_safety_alert_clears_active_block(): void
    {
        $zone = Zone::factory()->create();
        $alert = Alert::factory()->create([
            'zone_id' => $zone->id,
            'code' => 'biz_solution_temp_high',
            'status' => 'ACTIVE',
        ]);

        $result = app(AlertService::class)->resolveByCode($zone->id, 'biz_solution_temp_high', [
            'resolved_by' => 'history_logger',
            'resolved_via' => 'auto',
        ]);

        $this->assertTrue($result['resolved']);
        $alert->refresh();
        $this->assertSame('RESOLVED', $alert->status);
        $this->assertFalse(DB::table('alerts')
            ->where('zone_id', $zone->id)
            ->where('code', 'biz_solution_temp_high')
            ->where('status', 'ACTIVE')
            ->exists());
    }
}
