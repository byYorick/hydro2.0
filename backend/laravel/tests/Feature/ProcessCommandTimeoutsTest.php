<?php

namespace Tests\Feature;

use App\Models\Command;
use App\Models\DeviceNode;
use App\Models\Zone;
use Illuminate\Support\Facades\Config;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Event;
use Tests\RefreshDatabase;
use Tests\TestCase;

class ProcessCommandTimeoutsTest extends TestCase
{
    use RefreshDatabase;

    public function test_process_timeouts_marks_ack_command_as_timeout_with_terminal_metadata(): void
    {
        Config::set('commands.timeout_minutes', 5);

        $zone = Zone::factory()->create();
        $node = DeviceNode::query()->create([
            'zone_id' => $zone->id,
            'uid' => 'nd-test-irrig-1',
            'type' => 'irrig',
            'status' => 'online',
            'last_seen_at' => now()->subMinutes(3),
        ]);
        $command = Command::create([
            'zone_id' => $zone->id,
            'node_id' => $node->id,
            'cmd_id' => 'cmd-ack-timeout-001',
            'status' => Command::STATUS_ACK,
            'cmd' => 'test_command',
            'channel' => 'storage_state',
            'sent_at' => now()->subMinutes(10),
            'ack_at' => now()->subMinutes(9),
        ]);

        $this->artisan('commands:process-timeouts')
            ->assertExitCode(0);

        $command->refresh();
        $this->assertEquals(Command::STATUS_TIMEOUT, $command->status);
        $this->assertNotNull($command->failed_at);
        $this->assertEquals('command_timeout', $command->error_code);
        $this->assertEquals(1, $command->result_code);

        $this->assertDatabaseHas('zone_events', [
            'zone_id' => $zone->id,
            'type' => 'command_status',
            'entity_id' => 'cmd-ack-timeout-001',
        ]);

        $event = DB::table('zone_events')
            ->where('zone_id', $zone->id)
            ->where('type', 'command_status')
            ->latest('id')
            ->first();

        $payload = json_decode((string) $event->payload_json, true, 512, JSON_THROW_ON_ERROR);
        $this->assertSame('TIMEOUT', $payload['status']);
        $this->assertSame('command_timeout', $payload['error_code'] ?? null);
        $this->assertSame('nd-test-irrig-1', $payload['node_uid']);
        $this->assertSame('storage_state', $payload['channel']);
        $this->assertSame('online', $payload['node_status']);
        $this->assertTrue($payload['node_stale_online_candidate']);
        $this->assertIsInt($payload['node_last_seen_age_sec']);

        $this->assertDatabaseMissing('zone_events', [
            'zone_id' => $zone->id,
            'type' => 'COMMAND_TIMEOUT',
        ]);
    }

    public function test_process_timeouts_does_not_touch_recent_ack_command(): void
    {
        Config::set('commands.timeout_minutes', 5);

        $zone = Zone::factory()->create();
        $command = Command::create([
            'zone_id' => $zone->id,
            'cmd_id' => 'cmd-ack-recent-001',
            'status' => Command::STATUS_ACK,
            'cmd' => 'test_command',
            'sent_at' => now()->subMinutes(2),
            'ack_at' => now()->subMinute(),
        ]);

        $this->artisan('commands:process-timeouts')
            ->assertExitCode(0);

        $command->refresh();
        $this->assertEquals(Command::STATUS_ACK, $command->status);
        $this->assertNull($command->failed_at);

        $this->assertDatabaseMissing('zone_events', [
            'zone_id' => $zone->id,
            'type' => 'COMMAND_TIMEOUT',
        ]);
    }

    public function test_process_timeouts_does_not_overwrite_concurrent_done_transition(): void
    {
        Config::set('commands.timeout_minutes', 5);

        $zone = Zone::factory()->create();
        $command = Command::create([
            'zone_id' => $zone->id,
            'cmd_id' => 'cmd-timeout-race-done',
            'status' => Command::STATUS_ACK,
            'cmd' => 'run_pump',
            'sent_at' => now()->subMinutes(10),
            'ack_at' => now()->subMinutes(9),
        ]);

        $eventName = 'eloquent.retrieved: '.Command::class;
        Event::listen($eventName, function (Command $retrieved) use ($command): void {
            if ($retrieved->id !== $command->id) {
                return;
            }

            DB::table('commands')
                ->where('id', $command->id)
                ->update(['status' => Command::STATUS_DONE]);
        });

        try {
            $this->artisan('commands:process-timeouts')
                ->assertExitCode(0);
        } finally {
            Event::forget($eventName);
        }

        $command->refresh();
        $this->assertSame(Command::STATUS_DONE, $command->status);
        $this->assertNull($command->failed_at);
        $this->assertNull($command->error_code);
    }

    public function test_process_timeouts_dispatches_event_created_for_command_status(): void
    {
        Config::set('commands.timeout_minutes', 5);

        $zone = Zone::factory()->create();
        $node = DeviceNode::query()->create([
            'zone_id' => $zone->id,
            'uid' => 'nd-timeout-ws',
            'type' => 'irrig',
            'status' => 'online',
            'last_seen_at' => now()->subMinutes(3),
        ]);
        Command::create([
            'zone_id' => $zone->id,
            'node_id' => $node->id,
            'cmd_id' => 'cmd-timeout-ws',
            'status' => Command::STATUS_ACK,
            'cmd' => 'test_command',
            'channel' => 'pump_main',
            'sent_at' => now()->subMinutes(10),
            'ack_at' => now()->subMinutes(9),
        ]);

        $captured = [];
        Event::listen(\App\Events\EventCreated::class, function (\App\Events\EventCreated $event) use (&$captured): void {
            $captured[] = $event;
        });

        $this->artisan('commands:process-timeouts')
            ->assertExitCode(0);

        $this->assertCount(1, $captured);
        $this->assertSame('command_status', $captured[0]->kind);
        $this->assertSame($zone->id, $captured[0]->zoneId);
        $this->assertStringContainsString('cmd-timeout-ws', $captured[0]->message);
    }

    public function test_process_timeouts_keeps_timeout_when_side_effects_fail(): void
    {
        Config::set('commands.timeout_minutes', 5);

        $zone = Zone::factory()->create();
        $command = Command::create([
            'zone_id' => $zone->id,
            'cmd_id' => 'cmd-timeout-side-effect-fail',
            'status' => Command::STATUS_ACK,
            'cmd' => 'run_pump',
            'sent_at' => now()->subMinutes(10),
            'ack_at' => now()->subMinutes(9),
        ]);

        $eventName = 'eloquent.updated: '.Command::class;
        Event::listen($eventName, function () {
            throw new \RuntimeException('simulated observer failure');
        });

        try {
            $this->artisan('commands:process-timeouts')
                ->expectsOutputToContain('Processed 1 command(s)')
                ->assertExitCode(0);
        } finally {
            Event::forget($eventName);
        }

        $command->refresh();
        $this->assertSame(Command::STATUS_TIMEOUT, $command->status);
        $this->assertEquals('command_timeout', $command->error_code);
        $this->assertEquals(1, $command->result_code);
        $this->assertNotNull($command->failed_at);
    }

    public function test_process_timeouts_does_not_duplicate_timeout_on_rerun(): void
    {
        Config::set('commands.timeout_minutes', 5);

        $zone = Zone::factory()->create();
        $command = Command::create([
            'zone_id' => $zone->id,
            'cmd_id' => 'cmd-timeout-idempotent-rerun',
            'status' => Command::STATUS_SENT,
            'cmd' => 'run_pump',
            'sent_at' => now()->subMinutes(10),
        ]);

        $this->artisan('commands:process-timeouts')->assertExitCode(0);
        $command->refresh();
        $this->assertSame(Command::STATUS_TIMEOUT, $command->status);
        $failedAt = $command->failed_at;

        $eventsBefore = DB::table('zone_events')
            ->where('zone_id', $zone->id)
            ->where('type', 'command_status')
            ->where('entity_id', 'cmd-timeout-idempotent-rerun')
            ->count();

        $this->artisan('commands:process-timeouts')
            ->expectsOutputToContain('No commands found to timeout')
            ->assertExitCode(0);

        $command->refresh();
        $this->assertSame(Command::STATUS_TIMEOUT, $command->status);
        $this->assertEquals($failedAt?->toIso8601String(), $command->failed_at?->toIso8601String());

        $eventsAfter = DB::table('zone_events')
            ->where('zone_id', $zone->id)
            ->where('type', 'command_status')
            ->where('entity_id', 'cmd-timeout-idempotent-rerun')
            ->count();

        $this->assertSame($eventsBefore, $eventsAfter);
        $this->assertSame(1, $eventsBefore);
    }
}
