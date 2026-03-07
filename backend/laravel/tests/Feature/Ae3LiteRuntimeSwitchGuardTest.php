<?php

namespace Tests\Feature;

use App\Models\User;
use App\Models\Zone;
use Illuminate\Support\Facades\DB;
use Tests\RefreshDatabase;
use Tests\TestCase;

class Ae3LiteRuntimeSwitchGuardTest extends TestCase
{
    use RefreshDatabase;

    private function token(string $role = 'operator'): string
    {
        $user = User::factory()->create(['role' => $role]);
        $this->actingAs($user);

        return $user->createToken('test')->plainTextToken;
    }

    public function test_runtime_switch_is_denied_when_zone_has_active_ae3_task(): void
    {
        $token = $this->token();
        $zone = Zone::factory()->create([
            'status' => 'online',
            'automation_runtime' => 'ae2',
        ]);

        DB::table('ae_tasks')->insert([
            'zone_id' => $zone->id,
            'task_type' => 'cycle_start',
            'status' => 'waiting_command',
            'payload' => json_encode(['source' => 'test'], JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES),
            'idempotency_key' => 'ae3:task:'.$zone->id,
            'scheduled_for' => now(),
            'due_at' => now(),
            'claimed_by' => 'worker-a',
            'claimed_at' => now(),
            'created_at' => now(),
            'updated_at' => now(),
        ]);

        $resp = $this->withHeader('Authorization', 'Bearer '.$token)
            ->patchJson("/api/zones/{$zone->id}", ['automation_runtime' => 'ae3']);

        $resp->assertStatus(409)
            ->assertJsonPath('status', 'error')
            ->assertJsonPath('code', 'runtime_switch_denied_zone_busy')
            ->assertJsonPath('details.blocker', 'active_task')
            ->assertJsonPath('details.task_status', 'waiting_command');

        $this->assertSame('ae2', $zone->fresh()->automation_runtime);
    }

    public function test_runtime_switch_is_denied_when_zone_has_active_lease(): void
    {
        $token = $this->token();
        $zone = Zone::factory()->create([
            'status' => 'online',
            'automation_runtime' => 'ae3',
        ]);

        DB::table('ae_zone_leases')->insert([
            'zone_id' => $zone->id,
            'owner' => 'ae3-worker-a',
            'leased_until' => now()->addMinutes(5),
            'updated_at' => now(),
        ]);

        $resp = $this->withHeader('Authorization', 'Bearer '.$token)
            ->patchJson("/api/zones/{$zone->id}", ['automation_runtime' => 'ae2']);

        $resp->assertStatus(409)
            ->assertJsonPath('status', 'error')
            ->assertJsonPath('code', 'runtime_switch_denied_zone_busy')
            ->assertJsonPath('details.blocker', 'active_lease')
            ->assertJsonPath('details.owner', 'ae3-worker-a');

        $this->assertSame('ae3', $zone->fresh()->automation_runtime);
    }

    public function test_runtime_switch_is_denied_on_indeterminate_command_state(): void
    {
        $token = $this->token();
        $zone = Zone::factory()->create([
            'status' => 'online',
            'automation_runtime' => 'ae3',
        ]);

        $taskId = DB::table('ae_tasks')->insertGetId([
            'zone_id' => $zone->id,
            'task_type' => 'cycle_start',
            'status' => 'failed',
            'payload' => json_encode(['source' => 'test'], JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES),
            'idempotency_key' => 'ae3:cmd:'.$zone->id,
            'scheduled_for' => now(),
            'due_at' => now(),
            'claimed_by' => 'worker-a',
            'claimed_at' => now(),
            'error_code' => 'startup_recovery_unconfirmed_command',
            'error_message' => 'manual investigation required',
            'completed_at' => now(),
            'created_at' => now(),
            'updated_at' => now(),
        ]);

        DB::table('ae_commands')->insert([
            'task_id' => $taskId,
            'step_no' => 1,
            'node_uid' => 'nd-irrig-1',
            'channel' => 'pump_main',
            'payload' => json_encode(['cmd' => 'set_relay'], JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES),
            'publish_status' => 'pending',
            'created_at' => now(),
            'updated_at' => now(),
        ]);

        $resp = $this->withHeader('Authorization', 'Bearer '.$token)
            ->patchJson("/api/zones/{$zone->id}", ['automation_runtime' => 'ae2']);

        $resp->assertStatus(409)
            ->assertJsonPath('status', 'error')
            ->assertJsonPath('code', 'runtime_switch_denied_zone_busy')
            ->assertJsonPath('details.blocker', 'indeterminate_command_state')
            ->assertJsonPath('details.publish_status', 'pending')
            ->assertJsonPath('details.task_status', 'failed');

        $this->assertSame('ae3', $zone->fresh()->automation_runtime);
    }

    public function test_runtime_switch_succeeds_when_zone_is_idle(): void
    {
        $token = $this->token();
        $zone = Zone::factory()->create([
            'status' => 'online',
            'automation_runtime' => 'ae2',
        ]);

        $resp = $this->withHeader('Authorization', 'Bearer '.$token)
            ->patchJson("/api/zones/{$zone->id}", ['automation_runtime' => 'ae3']);

        $resp->assertOk()
            ->assertJsonPath('data.automation_runtime', 'ae3');

        $this->assertSame('ae3', $zone->fresh()->automation_runtime);
    }
}
