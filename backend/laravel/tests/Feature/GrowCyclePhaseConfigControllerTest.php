<?php

namespace Tests\Feature;

use App\Enums\GrowCycleStatus;
use App\Models\GrowCycle;
use App\Models\GrowCyclePhase;
use App\Models\User;
use App\Models\Zone;
use Illuminate\Support\Carbon;
use Tests\RefreshDatabase;
use Tests\TestCase;

/**
 * Phase 5.6: live edit активной recipe phase в live-режиме.
 */
class GrowCyclePhaseConfigControllerTest extends TestCase
{
    use RefreshDatabase;

    private function makeRunningCycleInLive(User $user): array
    {
        $zone = Zone::factory()->create([
            'control_mode' => 'manual',
            'config_mode' => 'live',
            'live_until' => Carbon::now()->addHours(1),
            'live_started_at' => Carbon::now(),
        ]);
        $cycle = GrowCycle::factory()->create([
            'zone_id' => $zone->id,
            'status' => GrowCycleStatus::RUNNING,
        ]);
        $phase = GrowCyclePhase::create([
            'grow_cycle_id' => $cycle->id,
            'phase_index' => 0,
            'name' => 'vegetative',
            'ph_target' => 6.0,
            'ec_target' => 1.8,
            'ph_min' => 5.5,
            'ph_max' => 6.5,
            'ec_min' => 1.5,
            'ec_max' => 2.1,
        ]);
        $cycle->forceFill(['current_phase_id' => $phase->id])->save();

        return [$zone, $cycle, $phase];
    }

    public function test_put_phase_config_locked_mode_conflict(): void
    {
        $user = User::factory()->create(['role' => 'agronomist']);
        $token = $user->createToken('t')->plainTextToken;
        [$zone, $cycle] = $this->makeRunningCycleInLive($user);
        $zone->forceFill(['config_mode' => 'locked', 'live_until' => null])->save();

        $resp = $this->actingAs($user)
            ->withHeader('Authorization', 'Bearer '.$token)
            ->putJson("/api/grow-cycles/{$cycle->id}/phase-config", [
                'reason' => 'tune ec',
                'ec_target' => 2.0,
            ]);

        $resp->assertStatus(409)->assertJsonPath('code', 'ZONE_NOT_IN_LIVE_MODE');
    }

    public function test_put_phase_config_operator_forbidden(): void
    {
        $user = User::factory()->create(['role' => 'operator']);
        $token = $user->createToken('t')->plainTextToken;
        [, $cycle] = $this->makeRunningCycleInLive($user);

        $resp = $this->actingAs($user)
            ->withHeader('Authorization', 'Bearer '.$token)
            ->putJson("/api/grow-cycles/{$cycle->id}/phase-config", [
                'reason' => 'tune',
                'ec_target' => 2.0,
            ]);

        // Middleware (role:admin,agronomist,engineer) отсекает первым.
        $resp->assertStatus(403);
    }

    public function test_put_phase_config_no_fields_provided(): void
    {
        $user = User::factory()->create(['role' => 'agronomist']);
        $token = $user->createToken('t')->plainTextToken;
        [, $cycle] = $this->makeRunningCycleInLive($user);

        $resp = $this->actingAs($user)
            ->withHeader('Authorization', 'Bearer '.$token)
            ->putJson("/api/grow-cycles/{$cycle->id}/phase-config", [
                'reason' => 'no-op',
            ]);

        $resp->assertStatus(422)->assertJsonPath('code', 'NO_FIELDS_PROVIDED');
    }

    public function test_put_phase_config_writes_fields_and_bumps_revision(): void
    {
        $user = User::factory()->create(['role' => 'agronomist']);
        $token = $user->createToken('t')->plainTextToken;
        [$zone, $cycle, $phase] = $this->makeRunningCycleInLive($user);
        $revisionBefore = (int) ($zone->config_revision ?? 1);

        $resp = $this->actingAs($user)
            ->withHeader('Authorization', 'Bearer '.$token)
            ->putJson("/api/grow-cycles/{$cycle->id}/phase-config", [
                'reason' => 'EC bump for flowering',
                'ec_target' => 2.2,
                'ec_min' => 2.0,
                'ec_max' => 2.4,
            ]);

        $resp->assertOk()
            ->assertJsonPath('grow_cycle_id', $cycle->id)
            ->assertJsonPath('phase_id', $phase->id);

        $phase->refresh();
        $this->assertSame('2.20', (string) $phase->ec_target);
        $this->assertSame('2.00', (string) $phase->ec_min);
        $this->assertSame('2.40', (string) $phase->ec_max);

        $zone->refresh();
        $this->assertGreaterThan($revisionBefore, (int) $zone->config_revision);

        $this->assertDatabaseHas('zone_config_changes', [
            'zone_id' => $zone->id,
            'namespace' => 'recipe.phase',
            'user_id' => $user->id,
        ]);
    }

    public function test_put_phase_config_rejects_non_editable_field(): void
    {
        $user = User::factory()->create(['role' => 'agronomist']);
        $token = $user->createToken('t')->plainTextToken;
        [, $cycle, $phase] = $this->makeRunningCycleInLive($user);

        $resp = $this->actingAs($user)
            ->withHeader('Authorization', 'Bearer '.$token)
            ->putJson("/api/grow-cycles/{$cycle->id}/phase-config", [
                'reason' => 'bad',
                'irrigation_mode' => 'drip',  // not in whitelist
            ]);

        $resp->assertStatus(422)->assertJsonPath('code', 'NO_FIELDS_PROVIDED');

        // Пагрубо: confirm что irrigation_mode НЕ изменился.
        $phase->refresh();
        $this->assertNull($phase->irrigation_mode);
    }
}
