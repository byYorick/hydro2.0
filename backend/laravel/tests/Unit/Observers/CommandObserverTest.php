<?php

namespace Tests\Unit\Observers;

use App\Events\CommandFailed;
use App\Events\CommandStatusUpdated;
use App\Events\EventCreated;
use App\Models\Command;
use App\Models\Zone;
use Illuminate\Support\Facades\Event;
use Illuminate\Support\Facades\DB;
use Tests\RefreshDatabase;
use Tests\TestCase;

class CommandObserverTest extends TestCase
{
    use RefreshDatabase;

    public function test_updated_to_error_dispatches_command_failed_with_catalog_fields(): void
    {
        Event::fake([CommandFailed::class, CommandStatusUpdated::class]);

        $zone = Zone::factory()->create();
        $command = Command::withoutEvents(fn () => Command::create([
            'cmd_id' => 'cmd-observer-error',
            'zone_id' => $zone->id,
            'status' => Command::STATUS_ACK,
            'cmd' => 'run_pump',
        ]));

        $command->update([
            'status' => Command::STATUS_ERROR,
            'error_code' => 'pump_busy',
            'error_message' => 'Pump is already running',
            'failed_at' => now(),
        ]);

        Event::assertDispatched(CommandFailed::class, 1);
        Event::assertDispatched(CommandFailed::class, function (CommandFailed $event): bool {
            return $event->commandId === 'cmd-observer-error'
                && $event->status === Command::STATUS_ERROR
                && $event->errorCode === 'pump_busy'
                && $event->error === 'Pump is already running'
                && $event->zoneId !== null;
        });
        Event::assertNotDispatched(CommandStatusUpdated::class);
    }

    public function test_updated_to_error_records_command_status_in_zone_events(): void
    {
        $zone = Zone::factory()->create();
        $command = Command::withoutEvents(fn () => Command::create([
            'cmd_id' => 'cmd-zone-event-error',
            'zone_id' => $zone->id,
            'status' => Command::STATUS_ACK,
            'cmd' => 'run_pump',
        ]));

        $command->update([
            'status' => Command::STATUS_ERROR,
            'error_code' => 'pump_busy',
            'error_message' => 'Pump is already running',
            'failed_at' => now(),
        ]);

        $this->assertDatabaseHas('zone_events', [
            'zone_id' => $zone->id,
            'type' => 'command_status',
            'entity_type' => 'command',
            'entity_id' => 'cmd-zone-event-error',
        ]);

        $event = DB::table('zone_events')
            ->where('zone_id', $zone->id)
            ->where('type', 'command_status')
            ->latest('id')
            ->first();

        $payload = json_decode((string) $event->payload_json, true, 512, JSON_THROW_ON_ERROR);
        $this->assertSame('ERROR', $payload['status']);
        $this->assertSame('pump_busy', $payload['error_code']);
        $this->assertSame('cmd-zone-event-error', $payload['cmd_id']);
    }

    public function test_updated_to_error_dispatches_event_created_for_live_events_feed(): void
    {
        $zone = Zone::factory()->create();
        $command = Command::withoutEvents(fn () => Command::create([
            'cmd_id' => 'cmd-event-created',
            'zone_id' => $zone->id,
            'status' => Command::STATUS_ACK,
            'cmd' => 'run_pump',
        ]));

        $captured = [];
        Event::listen(EventCreated::class, function (EventCreated $event) use (&$captured): void {
            $captured[] = $event;
        });

        $command->update([
            'status' => Command::STATUS_ERROR,
            'error_code' => 'pump_busy',
            'error_message' => 'Pump is already running',
            'failed_at' => now(),
        ]);

        $this->assertCount(1, $captured);
        $event = $captured[0];
        $this->assertSame($zone->id, $event->zoneId);
        $this->assertSame('command_status', $event->kind);
        $this->assertStringContainsString('Ошибка команды', $event->message);
        $this->assertStringContainsString('cmd-event-created', $event->message);

        $ledger = DB::table('zone_events')
            ->where('zone_id', $zone->id)
            ->where('type', 'command_status')
            ->latest('id')
            ->first();
        $payload = json_decode((string) $ledger->payload_json, true, 512, JSON_THROW_ON_ERROR);
        $this->assertSame($payload['ws_event_id'], $event->eventId);
        $this->assertSame((int) $ledger->server_ts, $event->serverTs);
    }

    public function test_updated_to_done_dispatches_command_status_updated_once(): void
    {
        Event::fake([CommandFailed::class, CommandStatusUpdated::class]);

        $zone = Zone::factory()->create();
        $command = Command::withoutEvents(fn () => Command::create([
            'cmd_id' => 'cmd-observer-done',
            'zone_id' => $zone->id,
            'status' => Command::STATUS_ACK,
            'cmd' => 'run_pump',
        ]));

        $command->update([
            'status' => Command::STATUS_DONE,
            'ack_at' => now(),
        ]);

        Event::assertDispatched(CommandStatusUpdated::class, 1);
        Event::assertNotDispatched(CommandFailed::class);
    }

    public function test_updated_to_timeout_without_scheduler_context_uses_node_diagnostics(): void
    {
        $zone = Zone::factory()->create();
        $node = \App\Models\DeviceNode::query()->create([
            'zone_id' => $zone->id,
            'uid' => 'nd-hl-timeout',
            'type' => 'irrig',
            'status' => 'online',
            'last_seen_at' => now()->subMinutes(2),
        ]);
        $command = Command::withoutEvents(fn () => Command::create([
            'cmd_id' => 'cmd-hl-timeout',
            'zone_id' => $zone->id,
            'node_id' => $node->id,
            'status' => Command::STATUS_ACK,
            'cmd' => 'run_pump',
            'channel' => 'pump_main',
            'sent_at' => now()->subMinutes(8),
        ]));

        $command->update([
            'status' => Command::STATUS_TIMEOUT,
            'error_code' => 'command_timeout',
            'failed_at' => now(),
        ]);

        $ledger = DB::table('zone_events')
            ->where('zone_id', $zone->id)
            ->where('type', 'command_status')
            ->latest('id')
            ->first();

        $payload = json_decode((string) $ledger->payload_json, true, 512, JSON_THROW_ON_ERROR);
        $this->assertSame('nd-hl-timeout', $payload['node_uid'] ?? null);
        $this->assertSame('pump_main', $payload['channel'] ?? null);
    }
}
