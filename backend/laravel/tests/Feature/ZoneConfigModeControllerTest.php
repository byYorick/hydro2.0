<?php

namespace Tests\Feature;

use App\Models\User;
use App\Models\Zone;
use App\Models\ZoneConfigChange;
use Illuminate\Support\Carbon;
use Tests\RefreshDatabase;
use Tests\TestCase;

class ZoneConfigModeControllerTest extends TestCase
{
    use RefreshDatabase;

    public function test_show_returns_default_locked_mode(): void
    {
        $user = User::factory()->create(['role' => 'viewer']);
        $token = $user->createToken('t')->plainTextToken;
        $zone = Zone::factory()->create();

        $response = $this->actingAs($user)
            ->withHeader('Authorization', 'Bearer '.$token)
            ->getJson("/api/zones/{$zone->id}/config-mode");

        $response->assertOk()
            ->assertJsonPath('config_mode', 'locked')
            ->assertJsonPath('config_revision', 1)
            ->assertJsonPath('live_until', null);
    }

    public function test_update_to_live_requires_agronomist_role(): void
    {
        $user = User::factory()->create(['role' => 'operator']);
        $token = $user->createToken('t')->plainTextToken;
        $zone = Zone::factory()->create(['control_mode' => 'manual']);

        $response = $this->actingAs($user)
            ->withHeader('Authorization', 'Bearer '.$token)
            ->patchJson("/api/zones/{$zone->id}/config-mode", [
                'mode' => 'live',
                'reason' => 'tuning experiment',
                'live_until' => Carbon::now()->addHour()->toIso8601String(),
            ]);

        $response->assertStatus(403)->assertJsonPath('code', 'FORBIDDEN_SET_LIVE');
    }

    public function test_update_to_live_blocked_when_control_mode_auto(): void
    {
        $user = User::factory()->create(['role' => 'agronomist']);
        $token = $user->createToken('t')->plainTextToken;
        $zone = Zone::factory()->create(['control_mode' => 'auto']);

        $response = $this->actingAs($user)
            ->withHeader('Authorization', 'Bearer '.$token)
            ->patchJson("/api/zones/{$zone->id}/config-mode", [
                'mode' => 'live',
                'reason' => 'tuning',
                'live_until' => Carbon::now()->addHour()->toIso8601String(),
            ]);

        $response->assertStatus(409)->assertJsonPath('code', 'CONFIG_MODE_CONFLICT_WITH_AUTO');
    }

    public function test_update_to_live_rejects_ttl_too_short(): void
    {
        $user = User::factory()->create(['role' => 'agronomist']);
        $token = $user->createToken('t')->plainTextToken;
        $zone = Zone::factory()->create(['control_mode' => 'manual']);

        $response = $this->actingAs($user)
            ->withHeader('Authorization', 'Bearer '.$token)
            ->patchJson("/api/zones/{$zone->id}/config-mode", [
                'mode' => 'live',
                'reason' => 'tuning',
                'live_until' => Carbon::now()->addSeconds(60)->toIso8601String(),
            ]);

        $response->assertStatus(422)->assertJsonPath('code', 'TTL_OUT_OF_RANGE');
    }

    public function test_update_to_live_rejects_ttl_too_long(): void
    {
        $user = User::factory()->create(['role' => 'agronomist']);
        $token = $user->createToken('t')->plainTextToken;
        $zone = Zone::factory()->create(['control_mode' => 'manual']);

        $response = $this->actingAs($user)
            ->withHeader('Authorization', 'Bearer '.$token)
            ->patchJson("/api/zones/{$zone->id}/config-mode", [
                'mode' => 'live',
                'reason' => 'tuning',
                'live_until' => Carbon::now()->addDays(8)->toIso8601String(),
            ]);

        $response->assertStatus(422)->assertJsonPath('code', 'TTL_OUT_OF_RANGE');
    }

    public function test_update_to_live_succeeds_with_valid_ttl(): void
    {
        $user = User::factory()->create(['role' => 'engineer']);
        $token = $user->createToken('t')->plainTextToken;
        $zone = Zone::factory()->create(['control_mode' => 'semi']);
        $liveUntil = Carbon::now()->addHours(2);

        $response = $this->actingAs($user)
            ->withHeader('Authorization', 'Bearer '.$token)
            ->patchJson("/api/zones/{$zone->id}/config-mode", [
                'mode' => 'live',
                'reason' => 'tuning EC setpoint',
                'live_until' => $liveUntil->toIso8601String(),
            ]);

        $response->assertOk()
            ->assertJsonPath('config_mode', 'live');

        $zone->refresh();
        $this->assertSame('live', $zone->config_mode);
        $this->assertNotNull($zone->live_until);
        $this->assertNotNull($zone->live_started_at);
        $this->assertSame($user->id, $zone->config_mode_changed_by);

        $this->assertDatabaseHas('zone_config_changes', [
            'zone_id' => $zone->id,
            'namespace' => 'zone.config_mode',
            'user_id' => $user->id,
        ]);
    }

    public function test_revert_to_locked_clears_live_until(): void
    {
        $user = User::factory()->create(['role' => 'agronomist']);
        $token = $user->createToken('t')->plainTextToken;
        $zone = Zone::factory()->create([
            'control_mode' => 'manual',
            'config_mode' => 'live',
            'live_until' => Carbon::now()->addHours(1),
            'live_started_at' => Carbon::now()->subMinutes(10),
        ]);

        $response = $this->actingAs($user)
            ->withHeader('Authorization', 'Bearer '.$token)
            ->patchJson("/api/zones/{$zone->id}/config-mode", [
                'mode' => 'locked',
                'reason' => 'done tuning',
            ]);

        $response->assertOk()->assertJsonPath('config_mode', 'locked');

        $zone->refresh();
        $this->assertSame('locked', $zone->config_mode);
        $this->assertNull($zone->live_until);
        $this->assertNull($zone->live_started_at);
    }

    public function test_extend_requires_live_mode(): void
    {
        $user = User::factory()->create(['role' => 'agronomist']);
        $token = $user->createToken('t')->plainTextToken;
        $zone = Zone::factory()->create(['config_mode' => 'locked']);

        $response = $this->actingAs($user)
            ->withHeader('Authorization', 'Bearer '.$token)
            ->patchJson("/api/zones/{$zone->id}/config-mode/extend", [
                'live_until' => Carbon::now()->addHours(2)->toIso8601String(),
            ]);

        $response->assertStatus(409)->assertJsonPath('code', 'NOT_IN_LIVE_MODE');
    }

    public function test_changes_returns_filtered_timeline(): void
    {
        $user = User::factory()->create(['role' => 'viewer']);
        $token = $user->createToken('t')->plainTextToken;
        $zone = Zone::factory()->create();

        ZoneConfigChange::create([
            'zone_id' => $zone->id, 'revision' => 1,
            'namespace' => 'zone.config_mode',
            'diff_json' => ['from' => 'locked', 'to' => 'live'],
            'user_id' => null, 'reason' => 'test',
            'created_at' => Carbon::now()->subMinutes(2),
        ]);
        ZoneConfigChange::create([
            'zone_id' => $zone->id, 'revision' => 2,
            'namespace' => 'zone.correction',
            'diff_json' => ['target_ec' => [1.5, 1.6]],
            'user_id' => null, 'reason' => 'tune',
            'created_at' => Carbon::now()->subMinutes(1),
        ]);

        $response = $this->actingAs($user)
            ->withHeader('Authorization', 'Bearer '.$token)
            ->getJson("/api/zones/{$zone->id}/config-changes?namespace=zone.correction");

        $response->assertOk()
            ->assertJsonCount(1, 'changes')
            ->assertJsonPath('changes.0.namespace', 'zone.correction');
    }
}
