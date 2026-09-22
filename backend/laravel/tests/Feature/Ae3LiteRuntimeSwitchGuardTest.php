<?php

namespace Tests\Feature;

use App\Exceptions\ZoneRuntimeSwitchDeniedException;
use App\Models\User;
use App\Models\Zone;
use App\Services\ZoneService;
use Illuminate\Support\Facades\DB;
use Tests\RefreshDatabase;
use Tests\TestCase;

/**
 * Допустимые runtime: ae3 и ae4. Неизвестное значение — 422.
 * Свободная зона принимает ae4. Задача или lease оставляют ZoneRuntimeSwitchDeniedException.
 */
class Ae3LiteRuntimeSwitchGuardTest extends TestCase
{
    use RefreshDatabase;

    private function token(string $role = 'operator'): string
    {
        $user = User::factory()->create(['role' => $role]);
        $this->actingAs($user);

        return $user->createToken('test')->plainTextToken;
    }

    public function test_setting_non_ae3_runtime_is_rejected_with_422(): void
    {
        $token = $this->token();
        $zone = Zone::factory()->create(['status' => 'online']);

        $resp = $this->withHeader('Authorization', 'Bearer '.$token)
            ->patchJson("/api/zones/{$zone->id}", ['automation_runtime' => 'legacy']);

        $resp->assertStatus(422);
        $this->assertSame('ae3', $zone->fresh()->automation_runtime);
    }

    public function test_setting_unknown_runtime_is_rejected_with_422(): void
    {
        $token = $this->token();
        $zone = Zone::factory()->create(['status' => 'online']);

        $resp = $this->withHeader('Authorization', 'Bearer '.$token)
            ->patchJson("/api/zones/{$zone->id}", ['automation_runtime' => 'legacy']);

        $resp->assertStatus(422);
        $this->assertSame('ae3', $zone->fresh()->automation_runtime);
    }

    public function test_noop_ae3_to_ae3_switch_succeeds_when_zone_is_idle(): void
    {
        $token = $this->token();
        $zone = Zone::factory()->create(['status' => 'online']);

        $resp = $this->withHeader('Authorization', 'Bearer '.$token)
            ->patchJson("/api/zones/{$zone->id}", ['automation_runtime' => 'ae3']);

        $resp->assertOk();
        $this->assertSame('ae3', $zone->fresh()->automation_runtime);
    }

    public function test_zones_automation_runtime_defaults_to_ae3(): void
    {
        $zone = Zone::factory()->create();
        $zone->refresh();

        $this->assertSame('ae3', $zone->automation_runtime);
    }

    public function test_control_mode_defaults_to_auto(): void
    {
        $zone = Zone::factory()->create();
        $zone->refresh();

        $this->assertSame('auto', $zone->control_mode ?? 'auto');
    }

    public function test_zones_db_constraint_rejects_non_ae3_runtime(): void
    {
        $zone = Zone::factory()->create(['status' => 'online']);

        $this->expectException(\Illuminate\Database\QueryException::class);
        DB::table('zones')
            ->where('id', $zone->id)
            ->update(['automation_runtime' => 'legacy']);
    }

    public function test_e215_idle_zone_accepts_ae4(): void
    {
        $token = $this->token();
        $zone = Zone::factory()->create(['status' => 'online']);

        $resp = $this->withHeader('Authorization', 'Bearer '.$token)
            ->patchJson("/api/zones/{$zone->id}", ['automation_runtime' => 'ae4']);

        $resp->assertOk();
        $this->assertSame('ae4', $zone->fresh()->automation_runtime);
    }

    public function test_e215_active_task_denies_runtime_switch(): void
    {
        $zone = Zone::factory()->create(['status' => 'online']);
        DB::table('ae_tasks')->insert([
            'zone_id' => $zone->id,
            'task_type' => 'cycle_start',
            'status' => 'pending',
            'idempotency_key' => 'e215-task-'.$zone->id,
            'scheduled_for' => now(),
            'due_at' => now(),
        ]);

        try {
            app(ZoneService::class)->update($zone, ['automation_runtime' => 'ae4']);
            $this->fail('Ожидался ZoneRuntimeSwitchDeniedException.');
        } catch (ZoneRuntimeSwitchDeniedException $exception) {
            $this->assertSame('active_task', $exception->details()['blocker']);
        }

        $this->assertSame('ae3', $zone->fresh()->automation_runtime);
    }

    public function test_e215_active_lease_denies_runtime_switch(): void
    {
        $zone = Zone::factory()->create(['status' => 'online']);
        DB::table('ae_zone_leases')->insert([
            'zone_id' => $zone->id,
            'owner' => 'e215-lease',
            'leased_until' => now()->addMinute(),
        ]);

        try {
            app(ZoneService::class)->update($zone, ['automation_runtime' => 'ae4']);
            $this->fail('Ожидался ZoneRuntimeSwitchDeniedException.');
        } catch (ZoneRuntimeSwitchDeniedException $exception) {
            $this->assertSame('active_lease', $exception->details()['blocker']);
        }

        $this->assertSame('ae3', $zone->fresh()->automation_runtime);
    }
}
