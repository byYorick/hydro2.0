<?php

namespace Tests\Feature;

use App\Models\User;
use App\Models\Zone;
use Illuminate\Support\Facades\DB;
use Laravel\Sanctum\Sanctum;
use Tests\RefreshDatabase;
use Tests\TestCase;

class ZoneProcessCalibrationControllerTest extends TestCase
{
    use RefreshDatabase;

    protected function setUp(): void
    {
        parent::setUp();

        $user = User::factory()->create(['role' => 'admin']);
        Sanctum::actingAs($user);
    }

    public function test_can_get_empty_process_calibration_list(): void
    {
        $zone = Zone::factory()->create();

        $response = $this->getJson("/api/zones/{$zone->id}/process-calibrations");

        $response->assertOk()
            ->assertJson([
                'status' => 'ok',
                'data' => [],
            ]);
    }

    public function test_can_upsert_process_calibration_for_mode(): void
    {
        $zone = Zone::factory()->create();

        $payload = [
            'ec_gain_per_ml' => 0.11,
            'ph_up_gain_per_ml' => 0.08,
            'ph_down_gain_per_ml' => 0.07,
            'ph_per_ec_ml' => -0.015,
            'ec_per_ph_ml' => 0.020,
            'transport_delay_sec' => 20,
            'settle_sec' => 45,
            'confidence' => 0.91,
            'source' => 'hil_manual',
            'meta' => [
                'batch' => 'cal-1',
                'observe' => [
                    'telemetry_period_sec' => 2,
                    'window_min_samples' => 3,
                    'decision_window_sec' => 6,
                    'observe_poll_sec' => 2,
                    'min_effect_fraction' => 0.25,
                    'stability_max_slope' => 0.05,
                    'no_effect_consecutive_limit' => 3,
                ],
            ],
        ];

        $response = $this->putJson("/api/zones/{$zone->id}/process-calibrations/tank_recirc", $payload);

        $response->assertOk()
            ->assertJsonPath('data.mode', 'tank_recirc')
            ->assertJsonPath('data.transport_delay_sec', 20)
            ->assertJsonPath('data.settle_sec', 45)
            ->assertJsonPath('data.confidence', 0.91)
            ->assertJsonPath('data.meta.observe.window_min_samples', 3);

        $this->assertDatabaseHas('zone_process_calibrations', [
            'zone_id' => $zone->id,
            'mode' => 'tank_recirc',
            'source' => 'hil_manual',
            'is_active' => true,
        ]);
        $this->assertDatabaseHas('zone_events', [
            'zone_id' => $zone->id,
            'type' => 'PROCESS_CALIBRATION_SAVED',
        ]);
    }

    public function test_upsert_normalizes_legacy_irrigating_alias_to_canonical_irrigation_mode(): void
    {
        $zone = Zone::factory()->create();

        $response = $this->putJson("/api/zones/{$zone->id}/process-calibrations/irrigating", [
            'ec_gain_per_ml' => 0.22,
            'transport_delay_sec' => 18,
        ]);

        $response->assertOk()
            ->assertJsonPath('data.mode', 'irrigation');

        $this->assertDatabaseHas('zone_process_calibrations', [
            'zone_id' => $zone->id,
            'mode' => 'irrigation',
            'ec_gain_per_ml' => 0.22,
            'transport_delay_sec' => 18,
            'is_active' => true,
        ]);
        $this->assertDatabaseMissing('zone_process_calibrations', [
            'zone_id' => $zone->id,
            'mode' => 'irrigating',
        ]);
    }

    public function test_upsert_deactivates_previous_active_calibration_for_same_mode(): void
    {
        $zone = Zone::factory()->create();
        $now = now()->subMinute();

        DB::table('zone_process_calibrations')->insert([
            'zone_id' => $zone->id,
            'mode' => 'tank_recirc',
            'ec_gain_per_ml' => 0.05,
            'source' => 'old',
            'valid_from' => $now,
            'valid_to' => null,
            'is_active' => true,
            'created_at' => $now,
            'updated_at' => $now,
        ]);

        $this->putJson("/api/zones/{$zone->id}/process-calibrations/tank_recirc", [
            'ec_gain_per_ml' => 0.12,
            'transport_delay_sec' => 12,
        ])->assertOk();

        $this->assertDatabaseCount('zone_process_calibrations', 2);
        $this->assertDatabaseHas('zone_process_calibrations', [
            'zone_id' => $zone->id,
            'mode' => 'tank_recirc',
            'source' => 'old',
            'is_active' => false,
        ]);
        $this->assertDatabaseHas('zone_process_calibrations', [
            'zone_id' => $zone->id,
            'mode' => 'tank_recirc',
            'is_active' => true,
            'transport_delay_sec' => 12,
        ]);
    }

    public function test_can_get_process_calibration_by_mode(): void
    {
        $zone = Zone::factory()->create();

        DB::table('zone_process_calibrations')->insert([
            'zone_id' => $zone->id,
            'mode' => 'solution_fill',
            'ec_gain_per_ml' => 0.10,
            'transport_delay_sec' => 15,
            'settle_sec' => 30,
            'confidence' => 0.75,
            'source' => 'manual',
            'valid_from' => now()->subMinute(),
            'valid_to' => null,
            'is_active' => true,
            'created_at' => now(),
            'updated_at' => now(),
        ]);

        $response = $this->getJson("/api/zones/{$zone->id}/process-calibrations/solution_fill");

        $response->assertOk()
            ->assertJsonPath('data.mode', 'solution_fill')
            ->assertJsonPath('data.transport_delay_sec', 15)
            ->assertJsonPath('data.confidence', 0.75);
    }

    public function test_rejects_invalid_process_calibration_mode(): void
    {
        $zone = Zone::factory()->create();

        $response = $this->putJson("/api/zones/{$zone->id}/process-calibrations/invalid-mode", [
            'ec_gain_per_ml' => 0.12,
        ]);

        $response->assertStatus(400)
            ->assertJson([
                'status' => 'error',
            ]);
    }

    public function test_validates_process_calibration_payload(): void
    {
        $zone = Zone::factory()->create();

        $response = $this->putJson("/api/zones/{$zone->id}/process-calibrations/generic", [
            'confidence' => 2,
            'transport_delay_sec' => 7200,
            'meta' => [
                'observe' => [
                    'window_min_samples' => 1,
                    'min_effect_fraction' => 0.001,
                ],
            ],
        ]);

        $response->assertStatus(422)
            ->assertJsonValidationErrors([
                'confidence',
                'transport_delay_sec',
                'meta.observe.window_min_samples',
                'meta.observe.min_effect_fraction',
            ]);
    }
}
