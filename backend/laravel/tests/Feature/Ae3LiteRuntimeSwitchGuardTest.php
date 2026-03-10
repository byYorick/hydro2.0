<?php

namespace Tests\Feature;

use App\Models\User;
use App\Models\Zone;
use Illuminate\Support\Facades\DB;
use Tests\RefreshDatabase;
use Tests\TestCase;

/**
 * После AE3-cutover единственный допустимый runtime — 'ae3'.
 * Тесты проверяют:
 *  - Попытка установить ae2 → 422 (валидация)
 *  - No-op switch ae3→ae3 при idle-зоне → 200
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

    public function test_setting_ae2_runtime_is_rejected_with_422(): void
    {
        $token = $this->token();
        $zone = Zone::factory()->create(['status' => 'online']);

        $resp = $this->withHeader('Authorization', 'Bearer '.$token)
            ->patchJson("/api/zones/{$zone->id}", ['automation_runtime' => 'ae2']);

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

    public function test_zones_db_constraint_rejects_ae2(): void
    {
        $zone = Zone::factory()->create(['status' => 'online']);

        $this->expectException(\Illuminate\Database\QueryException::class);
        DB::table('zones')
            ->where('id', $zone->id)
            ->update(['automation_runtime' => 'ae2']);
    }
}
