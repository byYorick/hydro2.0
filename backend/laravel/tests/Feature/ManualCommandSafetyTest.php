<?php

namespace Tests\Feature;

use App\Models\Command;
use App\Models\DeviceNode;
use App\Models\Sensor;
use App\Models\TelemetryLast;
use App\Models\User;
use App\Models\Zone;
use App\Models\ZoneEvent;
use App\Services\PythonBridgeService;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\RateLimiter;
use Tests\RefreshDatabase;
use Tests\TestCase;

class ManualCommandSafetyTest extends TestCase
{
    use RefreshDatabase;

    public function test_manual_dose_is_rejected_when_any_zone_node_has_estop(): void
    {
        [$zone, $node, $user] = $this->onlineDoseNode();
        DeviceNode::factory()->create([
            'zone_id' => $zone->id,
            'status' => 'online',
            'type' => 'irrig',
            'uid' => 'nd-estop-peer',
        ]);
        ZoneEvent::query()->create([
            'zone_id' => $zone->id,
            'type' => 'EMERGENCY_STOP_ACTIVATED',
            'payload_json' => ['source' => 'node', 'node_uid' => 'nd-estop-peer'],
            'created_at' => now(),
        ]);

        $this->mock(PythonBridgeService::class, function ($mock): void {
            $mock->shouldNotReceive('sendNodeCommand');
        });

        $response = $this->actingAs($user)->postJson("/api/nodes/{$node->id}/commands", [
            'cmd' => 'dose',
            'channel' => 'pump_acid',
            'params' => ['ml' => 1],
        ]);

        $response->assertStatus(409)
            ->assertJsonPath('status', 'error')
            ->assertJsonPath('code', 'estop_active')
            ->assertJsonPath('data.node_uid', 'nd-estop-peer');

        $this->assertDatabaseHas('system_logs', [
            'message' => 'manual_command_rejected',
        ]);
        $log = DB::table('system_logs')->where('message', 'manual_command_rejected')->first();
        $context = json_decode((string) $log->context, true);
        $this->assertSame((int) $zone->id, (int) ($context['zone_id'] ?? 0));
        $this->assertSame((int) $user->id, (int) ($context['user_id'] ?? 0));
        $this->assertSame('rejected', $context['result'] ?? null);
        $encoded = json_encode($context);
        $this->assertIsString($encoded);
        $this->assertStringNotContainsString('node_secret', $encoded);
        $this->assertStringNotContainsString('signature', $encoded);
    }

    public function test_manual_dose_above_single_limit_is_rejected_and_audited(): void
    {
        [$zone, $node, $user] = $this->onlineDoseNode();
        $this->mock(PythonBridgeService::class, function ($mock): void {
            $mock->shouldNotReceive('sendNodeCommand');
        });

        $response = $this->actingAs($user)->postJson("/api/nodes/{$node->id}/commands", [
            'cmd' => 'dose',
            'channel' => 'pump_acid',
            'params' => ['ml' => 100],
        ]);

        $response->assertStatus(422)
            ->assertJsonPath('code', 'dose_limit_exceeded')
            ->assertJsonPath('data.limit_ml', 35);

        $this->assertDatabaseHas('zone_events', [
            'zone_id' => $zone->id,
            'type' => 'MANUAL_COMMAND_REJECTED',
        ]);
    }

    public function test_manual_dose_above_window_aggregate_is_rejected(): void
    {
        [, $node, $user] = $this->onlineDoseNode();
        $previous = Command::withoutEvents(fn () => Command::query()->create([
            'cmd_id' => 'cmd-window-prev',
            'zone_id' => $node->zone_id,
            'node_id' => $node->id,
            'channel' => 'pump_acid',
            'cmd' => 'dose',
            'status' => Command::STATUS_DONE,
            'params' => ['ml' => 280],
        ]));
        DB::table('commands')->where('id', $previous->id)->update([
            'created_at' => now()->subMinutes(10),
        ]);

        $this->mock(PythonBridgeService::class, function ($mock): void {
            $mock->shouldNotReceive('sendNodeCommand');
        });

        $response = $this->actingAs($user)->postJson("/api/nodes/{$node->id}/commands", [
            'cmd' => 'dose',
            'channel' => 'pump_acid',
            'params' => ['ml' => 1],
        ]);

        $response->assertStatus(422)
            ->assertJsonPath('code', 'dose_window_limit_exceeded')
            ->assertJsonPath('data.used_ml', 280)
            ->assertJsonPath('data.limit_ml', 280);
    }

    public function test_manual_commands_are_rate_limited_per_zone(): void
    {
        config(['manual_safety.rate_per_minute' => 2]);
        [, $node, $user] = $this->onlineDoseNode();
        RateLimiter::clear('manual-actuator:zone:'.$node->zone_id.':user:'.$user->id);

        $this->mock(PythonBridgeService::class, function ($mock): void {
            $mock->shouldReceive('sendNodeCommand')->twice()->andReturn('cmd-rate-ok');
        });

        $payload = [
            'cmd' => 'dose',
            'channel' => 'pump_acid',
            'params' => ['ml' => 1],
        ];

        $this->actingAs($user)->postJson("/api/nodes/{$node->id}/commands", $payload)->assertOk();
        $this->actingAs($user)->postJson("/api/nodes/{$node->id}/commands", $payload)->assertOk();
        $this->actingAs($user)->postJson("/api/nodes/{$node->id}/commands", $payload)
            ->assertStatus(429)
            ->assertJsonPath('code', 'manual_command_rate_limited');
    }

    public function test_manual_dose_is_rejected_when_node_is_offline(): void
    {
        [, $node, $user] = $this->onlineDoseNode();
        $node->status = 'offline';
        $node->save();

        $this->mock(PythonBridgeService::class, function ($mock): void {
            $mock->shouldNotReceive('sendNodeCommand');
        });

        $this->actingAs($user)->postJson("/api/nodes/{$node->id}/commands", [
            'cmd' => 'dose',
            'channel' => 'pump_acid',
            'params' => ['ml' => 1],
        ])->assertStatus(409)
            ->assertJsonPath('code', 'node_offline');
    }

    public function test_unknown_node_command_and_unexpected_params_are_422(): void
    {
        [, $node, $user] = $this->onlineDoseNode();

        $this->actingAs($user)->postJson("/api/nodes/{$node->id}/commands", [
            'cmd' => 'explode_pump',
            'params' => [],
        ])->assertStatus(422)
            ->assertJsonValidationErrors(['cmd']);

        $this->actingAs($user)->postJson("/api/nodes/{$node->id}/commands", [
            'cmd' => 'dose',
            'channel' => 'pump_acid',
            'params' => ['ml' => 1, 'duration_ms' => 1000],
        ])->assertStatus(422)
            ->assertJsonValidationErrors(['params.duration_ms']);
    }

    public function test_manual_dose_within_limits_is_allowed(): void
    {
        [, $node, $user] = $this->onlineDoseNode();
        $this->mock(PythonBridgeService::class, function ($mock): void {
            $mock->shouldReceive('sendNodeCommand')->once()->andReturn('cmd-dose-ok');
        });

        $this->actingAs($user)->postJson("/api/nodes/{$node->id}/commands", [
            'cmd' => 'dose',
            'channel' => 'pump_acid',
            'params' => ['ml' => 1],
        ])->assertOk()
            ->assertJsonPath('data.command_id', 'cmd-dose-ok');
    }

    public function test_fail_safe_off_is_allowed_while_estop_is_active(): void
    {
        [$zone, $node, $user] = $this->onlineDoseNode();
        ZoneEvent::query()->create([
            'zone_id' => $zone->id,
            'type' => 'EMERGENCY_STOP_ACTIVATED',
            'payload_json' => ['source' => 'node', 'node_uid' => $node->uid],
            'created_at' => now(),
        ]);

        $this->mock(PythonBridgeService::class, function ($mock): void {
            $mock->shouldReceive('sendNodeCommand')->once()->andReturn('cmd-off-ok');
        });

        $this->actingAs($user)->postJson("/api/nodes/{$node->id}/commands", [
            'cmd' => 'set_relay',
            'channel' => 'valve_irrigation',
            'params' => ['state' => false],
        ])->assertOk()
            ->assertJsonPath('data.command_id', 'cmd-off-ok');
    }

    public function test_irrigation_is_rejected_when_solution_min_is_low(): void
    {
        [$zone, $node, $user] = $this->onlineDoseNode();
        $node->type = 'irrig';
        $node->save();
        $sensor = Sensor::factory()->create([
            'greenhouse_id' => $zone->greenhouse_id,
            'zone_id' => $zone->id,
            'node_id' => $node->id,
            'type' => 'WATER_LEVEL',
            'label' => 'level_solution_min',
            'is_active' => true,
        ]);
        TelemetryLast::query()->create([
            'sensor_id' => $sensor->id,
            'last_value' => 0,
            'last_ts' => now(),
            'last_quality' => 'GOOD',
        ]);

        $this->mock(PythonBridgeService::class, function ($mock): void {
            $mock->shouldNotReceive('sendNodeCommand');
            $mock->shouldNotReceive('sendZoneCommand');
        });

        $this->actingAs($user)->postJson("/api/nodes/{$node->id}/commands", [
            'cmd' => 'run_pump',
            'channel' => 'pump_main',
            'params' => ['duration_ms' => 3000],
        ])->assertStatus(409)
            ->assertJsonPath('code', 'solution_level_interlock');
    }

    /**
     * @return array{0: Zone, 1: DeviceNode, 2: User}
     */
    private function onlineDoseNode(): array
    {
        $zone = Zone::factory()->create();
        $node = DeviceNode::factory()->create([
            'zone_id' => $zone->id,
            'status' => 'online',
            'type' => 'ph',
        ]);
        $user = User::factory()->create(['role' => 'operator']);

        return [$zone, $node, $user];
    }
}
