<?php

namespace Tests\Feature;

use App\Models\User;
use App\Models\Zone;
use App\Services\AutomationConfigDocumentService;
use App\Services\AutomationConfigRegistry;
use Illuminate\Support\Carbon;
use Tests\RefreshDatabase;
use Tests\TestCase;

/**
 * Phase 6.2: live edit полный fine-tuning correction.
 * Whitelist использует категориальные пути из `base_config.*`
 * (retry/timing/dosing/safety/tolerance/controllers) или `phase_overrides.{phase}.*`.
 */
class ZoneCorrectionLiveEditControllerTest extends TestCase
{
    use RefreshDatabase;

    private function zoneInLive(): Zone
    {
        return Zone::factory()->create([
            'control_mode' => 'manual',
            'config_mode' => 'live',
            'live_until' => Carbon::now()->addHours(1),
            'live_started_at' => Carbon::now(),
        ]);
    }

    /** Материализует defaults через registry — резолвер строит полную base_config structure. */
    private function seedDefaults(Zone $zone): void
    {
        app(AutomationConfigDocumentService::class)->getDocument(
            AutomationConfigRegistry::NAMESPACE_ZONE_CORRECTION,
            AutomationConfigRegistry::SCOPE_ZONE,
            $zone->id,
            true,
        );
    }

    public function test_requires_live_mode(): void
    {
        $user = User::factory()->create(['role' => 'agronomist']);
        $token = $user->createToken('t')->plainTextToken;
        $zone = Zone::factory()->create(['control_mode' => 'auto', 'config_mode' => 'locked']);
        $this->seedDefaults($zone);

        $resp = $this->actingAs($user)->withHeader('Authorization', 'Bearer '.$token)
            ->putJson("/api/zones/{$zone->id}/correction/live-edit", [
                'reason' => 'tune',
                'correction_patch' => ['timing.stabilization_sec' => 120],
            ]);

        $resp->assertStatus(409)->assertJsonPath('code', 'ZONE_NOT_IN_LIVE_MODE');
    }

    public function test_no_fields_rejected(): void
    {
        $user = User::factory()->create(['role' => 'agronomist']);
        $token = $user->createToken('t')->plainTextToken;
        $zone = $this->zoneInLive();
        $this->seedDefaults($zone);

        $resp = $this->actingAs($user)->withHeader('Authorization', 'Bearer '.$token)
            ->putJson("/api/zones/{$zone->id}/correction/live-edit", [
                'reason' => 'no-op',
            ]);

        $resp->assertStatus(422)->assertJsonPath('code', 'NO_FIELDS_PROVIDED');
    }

    public function test_non_whitelisted_path_rejected(): void
    {
        $user = User::factory()->create(['role' => 'agronomist']);
        $token = $user->createToken('t')->plainTextToken;
        $zone = $this->zoneInLive();
        $this->seedDefaults($zone);

        $resp = $this->actingAs($user)->withHeader('Authorization', 'Bearer '.$token)
            ->putJson("/api/zones/{$zone->id}/correction/live-edit", [
                'reason' => 'try dosing mode change',
                'correction_patch' => ['dosing.ec_dosing_mode' => 'multi_parallel'],
            ]);

        $resp->assertStatus(422)->assertJsonPath('code', 'PATH_NOT_WHITELISTED');
    }

    public function test_base_config_categorical_paths_applied(): void
    {
        $user = User::factory()->create(['role' => 'agronomist']);
        $token = $user->createToken('t')->plainTextToken;
        $zone = $this->zoneInLive();
        $this->seedDefaults($zone);

        $resp = $this->actingAs($user)->withHeader('Authorization', 'Bearer '.$token)
            ->putJson("/api/zones/{$zone->id}/correction/live-edit", [
                'reason' => 'full fine-tuning',
                'correction_patch' => [
                    'timing.stabilization_sec' => 45,
                    'retry.telemetry_stale_retry_sec' => 20,
                    'controllers.ec.kp' => 0.7,
                    'controllers.ec.observe.decision_window_sec' => 12,
                    'controllers.ec.overshoot_guard.hard_max' => 9.5,
                ],
            ]);

        $resp->assertOk();

        $doc = app(AutomationConfigDocumentService::class)->getDocument(
            AutomationConfigRegistry::NAMESPACE_ZONE_CORRECTION,
            AutomationConfigRegistry::SCOPE_ZONE,
            $zone->id,
            false,
        );
        $this->assertSame(45, data_get($doc->payload, 'base_config.timing.stabilization_sec'));
        $this->assertSame(20, data_get($doc->payload, 'base_config.retry.telemetry_stale_retry_sec'));
        $this->assertSame(0.7, data_get($doc->payload, 'base_config.controllers.ec.kp'));
        $this->assertSame(12, data_get($doc->payload, 'base_config.controllers.ec.observe.decision_window_sec'));
        $this->assertSame(9.5, data_get($doc->payload, 'base_config.controllers.ec.overshoot_guard.hard_max'));

        // resolved_config тоже обновлён (resolver пересобирает после upsert)
        $this->assertSame(45, data_get($doc->payload, 'resolved_config.base.timing.stabilization_sec'));
    }

    public function test_phase_override_path_applied(): void
    {
        $user = User::factory()->create(['role' => 'engineer']);
        $token = $user->createToken('t')->plainTextToken;
        $zone = $this->zoneInLive();
        $this->seedDefaults($zone);

        $resp = $this->actingAs($user)->withHeader('Authorization', 'Bearer '.$token)
            ->putJson("/api/zones/{$zone->id}/correction/live-edit", [
                'reason' => 'tank_recirc phase tune',
                'phase' => 'tank_recirc',
                'correction_patch' => [
                    'timing.stabilization_sec' => 150,
                    'controllers.ph.kp' => 0.35,
                ],
            ]);

        $resp->assertOk();

        $doc = app(AutomationConfigDocumentService::class)->getDocument(
            AutomationConfigRegistry::NAMESPACE_ZONE_CORRECTION,
            AutomationConfigRegistry::SCOPE_ZONE,
            $zone->id,
            false,
        );
        $this->assertSame(150, data_get($doc->payload, 'phase_overrides.tank_recirc.timing.stabilization_sec'));
        $this->assertSame(0.35, data_get($doc->payload, 'phase_overrides.tank_recirc.controllers.ph.kp'));
    }

    public function test_calibration_patch_requires_phase(): void
    {
        $user = User::factory()->create(['role' => 'agronomist']);
        $token = $user->createToken('t')->plainTextToken;
        $zone = $this->zoneInLive();
        $this->seedDefaults($zone);

        $resp = $this->actingAs($user)->withHeader('Authorization', 'Bearer '.$token)
            ->putJson("/api/zones/{$zone->id}/correction/live-edit", [
                'reason' => 'transport delay tune',
                'calibration_patch' => ['transport_delay_sec' => 5],
            ]);

        $resp->assertStatus(422)->assertJsonPath('code', 'CALIBRATION_PHASE_REQUIRED');
    }

    public function test_calibration_phase_tank_recirc_applies(): void
    {
        $user = User::factory()->create(['role' => 'agronomist']);
        $token = $user->createToken('t')->plainTextToken;
        $zone = $this->zoneInLive();
        $this->seedDefaults($zone);

        $resp = $this->actingAs($user)->withHeader('Authorization', 'Bearer '.$token)
            ->putJson("/api/zones/{$zone->id}/correction/live-edit", [
                'reason' => 'tune transport delay + settle',
                'phase' => 'tank_recirc',
                'calibration_patch' => [
                    'transport_delay_sec' => 6,
                    'settle_sec' => 15,
                ],
            ]);

        $resp->assertOk()->assertJsonPath('affected_fields.calibration.0', 'transport_delay_sec');

        $doc = app(AutomationConfigDocumentService::class)->getDocument(
            AutomationConfigRegistry::NAMESPACE_ZONE_PROCESS_CALIBRATION_TANK_RECIRC,
            AutomationConfigRegistry::SCOPE_ZONE,
            $zone->id,
            false,
        );
        $this->assertSame(6, data_get($doc->payload, 'transport_delay_sec'));
        $this->assertSame(15, data_get($doc->payload, 'settle_sec'));

        $this->assertDatabaseHas('zone_config_changes', [
            'zone_id' => $zone->id,
            'namespace' => 'zone.correction.live',
            'user_id' => $user->id,
        ]);
    }

    public function test_combined_correction_and_calibration_single_revision_bump(): void
    {
        $user = User::factory()->create(['role' => 'agronomist']);
        $token = $user->createToken('t')->plainTextToken;
        $zone = $this->zoneInLive();
        $this->seedDefaults($zone);
        $revisionBefore = (int) ($zone->config_revision ?? 1);

        $resp = $this->actingAs($user)->withHeader('Authorization', 'Bearer '.$token)
            ->putJson("/api/zones/{$zone->id}/correction/live-edit", [
                'reason' => 'both',
                'phase' => 'tank_recirc',
                'correction_patch' => [
                    'timing.stabilization_sec' => 75,
                    'controllers.ec.observe.decision_window_sec' => 14,
                ],
                'calibration_patch' => [
                    'transport_delay_sec' => 4,
                ],
            ]);

        $resp->assertOk();

        $zone->refresh();
        // Single bumpAndAudit — revision++ ровно один раз
        $this->assertSame($revisionBefore + 1, (int) $zone->config_revision);
    }
}
