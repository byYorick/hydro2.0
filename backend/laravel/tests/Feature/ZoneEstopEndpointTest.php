<?php

namespace Tests\Feature;

use App\Models\Command;
use App\Models\DeviceNode;
use App\Models\User;
use App\Models\Zone;
use App\Models\ZoneEvent;
use App\Services\PythonBridgeService;
use App\Services\ZoneEstopService;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Gate;
use Illuminate\Support\Str;
use Tests\RefreshDatabase;
use Tests\TestCase;

class ZoneEstopEndpointTest extends TestCase
{
    use RefreshDatabase;

    public function test_operator_can_engage_and_release_estop_and_each_call_is_audited(): void
    {
        $zone = Zone::factory()->create();
        $user = User::factory()->create(['role' => 'operator']);

        $this->mock(PythonBridgeService::class, function ($mock): void {
            $mock->shouldReceive('sendNodeCommand')->once()->withArgs(fn ($node, $payload) => $payload['cmd'] === 'exit_safe_mode' && $payload['channel'] === 'system')->andReturn((string) Str::uuid());
        });

        $engaged = $this->actingAs($user)->postJson("/api/zones/{$zone->id}/estop", [
            'action' => 'engage',
            'reason' => 'дым в шкафу',
        ]);

        $engaged->assertOk()
            ->assertJsonPath('data.action', 'engage')
            ->assertJsonPath('data.result', 'engaged')
            ->assertJsonPath('data.estop.active', true)
            ->assertJsonPath('data.estop.source', 'operator');

        $this->assertDatabaseHas('zone_events', [
            'zone_id' => $zone->id,
            'type' => 'EMERGENCY_STOP_ACTIVATED',
        ]);
        $this->assertAudit($zone->id, $user->id, 'engage', 'engaged');

        $node = DeviceNode::factory()->create([
            'zone_id' => $zone->id,
            'status' => 'online',
            'type' => 'ph',
        ]);
        $this->actingAs($user)->postJson("/api/nodes/{$node->id}/commands", [
            'cmd' => 'dose',
            'channel' => 'pump_acid',
            'params' => ['ml' => 1],
        ])->assertStatus(409)->assertJsonPath('code', 'estop_active');

        $released = $this->actingAs($user)->postJson("/api/zones/{$zone->id}/estop", [
            'action' => 'release',
            'reason' => 'дым устранён',
        ]);
        $released->assertOk()
            ->assertJsonPath('data.result', 'released')
            ->assertJsonPath('data.estop.active', false);
        $this->assertAudit($zone->id, $user->id, 'release', 'released');

        $this->getJson("/api/zones/{$zone->id}/estop")
            ->assertOk()
            ->assertJsonPath('data.estop.active', false);
    }

    public function test_release_without_reason_is_422(): void
    {
        $zone = Zone::factory()->create();
        $user = User::factory()->create(['role' => 'operator']);

        $this->actingAs($user)->postJson("/api/zones/{$zone->id}/estop", [
            'action' => 'release',
            'reason' => 'ok',
        ])->assertStatus(422)->assertJsonValidationErrors(['reason']);
    }

    public function test_policy_allows_operator_and_denies_viewer_and_stranger(): void
    {
        $zone = Zone::factory()->create();
        $operator = User::factory()->create(['role' => 'operator']);
        $viewer = User::factory()->create(['role' => 'viewer']);
        $stranger = User::factory()->create(['role' => 'operator']);
        $this->revokeZone($stranger, $zone);

        $this->assertTrue(Gate::forUser($operator)->allows('engageEstop', $zone));
        $this->assertTrue(Gate::forUser($operator)->allows('releaseEstop', $zone));
        $this->assertFalse(Gate::forUser($viewer)->allows('engageEstop', $zone));
        $this->assertFalse(Gate::forUser($stranger)->allows('engageEstop', $zone));
        $this->assertFalse(Gate::forUser($stranger)->allows('releaseEstop', $zone));

        $this->actingAs($viewer)->postJson("/api/zones/{$zone->id}/estop", [
            'action' => 'engage',
        ])->assertStatus(403);

        $this->actingAs($stranger)->postJson("/api/zones/{$zone->id}/estop", [
            'action' => 'engage',
        ])->assertStatus(403);
    }

    public function test_stop_reaches_online_and_offline_nodes_and_requires_terminal_done(): void
    {
        $zone = Zone::factory()->create();
        $user = User::factory()->create(['role' => 'operator']);
        $nodes = collect(['online', 'offline'])->map(fn ($status) => DeviceNode::factory()->create([
            'zone_id' => $zone->id, 'status' => $status, 'type' => 'ph',
        ]));
        $this->mock(PythonBridgeService::class, function ($mock) use ($zone): void {
            $mock->shouldReceive('sendNodeCommand')->twice()->withArgs(function ($node, $payload) use ($zone): bool {
                // The global admission latch is committed before dispatch.
                $this->assertTrue(app(ZoneEstopService::class)->status($zone)['active']);

                return $payload['cmd'] === 'enter_safe_mode' && $payload['channel'] === 'system';
            })->andReturnUsing(function ($node, $payload): string {
                $id = (string) Str::uuid();
                Command::create(['zone_id' => $node->zone_id, 'node_id' => $node->id,
                    'cmd_id' => $id, 'cmd' => $payload['cmd'], 'channel' => 'system', 'status' => 'SENT']);

                return $id;
            });
        });
        $this->actingAs($user)->postJson("/api/zones/{$zone->id}/estop", ['action' => 'engage'])
            ->assertOk()->assertJsonPath('data.estop.stop_status', 'pending');
        Command::query()->update(['status' => 'ACK']);
        $this->getJson("/api/zones/{$zone->id}/estop")->assertJsonPath('data.estop.stop_status', 'pending');
        Command::query()->update(['status' => 'DONE']);
        $this->getJson("/api/zones/{$zone->id}/estop")->assertJsonPath('data.estop.stop_status', 'confirmed');
        ZoneEvent::create(['zone_id' => $zone->id, 'type' => 'EMERGENCY_STOP_RELEASED',
            'payload_json' => ['source' => 'node_event'], 'created_at' => now()->addSecond()]);
        $this->getJson("/api/zones/{$zone->id}/estop")->assertJsonPath('data.estop.active', true);
        Command::query()->update(['status' => 'ERROR']);
        $this->getJson("/api/zones/{$zone->id}/estop")
            ->assertJsonPath('data.estop.active', true)->assertJsonPath('data.estop.stop_status', 'failed');
    }

    public function test_stop_delivery_failure_keeps_latch_and_is_visible(): void
    {
        $zone = Zone::factory()->create();
        DeviceNode::factory()->create(['zone_id' => $zone->id, 'type' => 'climate']);
        $this->mock(PythonBridgeService::class, function ($mock): void {
            $mock->shouldReceive('sendNodeCommand')->once()->andThrow(new \RuntimeException('HL unavailable'));
        });
        $this->actingAs(User::factory()->create(['role' => 'operator']))
            ->postJson("/api/zones/{$zone->id}/estop", ['action' => 'engage'])
            ->assertOk()->assertJsonPath('data.estop.active', true)->assertJsonPath('data.estop.stop_status', 'failed');
    }

    public function test_release_is_blocked_while_ae_task_is_running(): void
    {
        $zone = Zone::factory()->create();
        DB::table('ae_zone_leases')->insert(['zone_id' => $zone->id, 'owner' => 'test-worker',
            'leased_until' => now()->addMinute(), 'updated_at' => now()]);
        $this->mock(PythonBridgeService::class, fn ($mock) => $mock->shouldNotReceive('sendNodeCommand'));
        $this->actingAs(User::factory()->create(['role' => 'operator']))
            ->postJson("/api/zones/{$zone->id}/estop", ['action' => 'release', 'reason' => 'опасность устранена'])
            ->assertStatus(409)->assertJsonPath('code', 'ae3_zone_lease_held');
    }

    private function assertAudit(int $zoneId, int $userId, string $action, string $result): void
    {
        $log = DB::table('system_logs')
            ->where('message', 'zone_estop')
            ->orderByDesc('id')
            ->first();
        $this->assertNotNull($log);
        $context = json_decode((string) $log->context, true);
        $this->assertSame($zoneId, (int) ($context['zone_id'] ?? 0));
        $this->assertSame($userId, (int) ($context['user_id'] ?? 0));
        $this->assertSame($action, $context['details']['action'] ?? null);
        $this->assertSame($result, $context['result'] ?? null);
        $this->assertNotEmpty($context['at'] ?? null);
    }

    private function revokeZone(User $user, Zone $zone): void
    {
        DB::table('user_zones')->where('user_id', $user->id)->where('zone_id', $zone->id)->delete();
        if ($zone->greenhouse_id) {
            DB::table('user_greenhouses')->where('user_id', $user->id)->where('greenhouse_id', $zone->greenhouse_id)->delete();
        }
    }
}
