<?php

namespace Tests\Feature\Broadcasting;

use App\Events\AlertCreated;
use App\Events\CommandFailed;
use App\Events\CommandStatusUpdated;
use App\Events\EventCreated;
use App\Events\NodeConfigUpdated;
use App\Events\ZoneUpdated;
use App\Models\DeviceNode;
use App\Models\Zone;
use Illuminate\Support\Carbon;
use Tests\TestCase;

class EventBroadcastTest extends TestCase
{
    protected function makeZone(int $id, string $status = 'RUNNING', string $name = 'Delta'): Zone
    {
        $zone = new Zone;
        $zone->id = $id;
        $zone->forceFill([
            'name' => $name,
            'status' => $status,
        ]);

        return $zone;
    }

    protected function makeDeviceNode(int $id, int $zoneId): DeviceNode
    {
        $node = new DeviceNode;
        $node->id = $id;
        $node->forceFill([
            'uid' => "nd-{$id}",
            'name' => 'Irrigation Controller',
            'type' => 'irrigation',
            'status' => 'online',
            'fw_version' => '1.0.0',
            'zone_id' => $zoneId,
        ]);
        $node->wasRecentlyCreated = true;

        return $node;
    }

    public function test_alert_created_broadcasts_public_alert_channel(): void
    {
        $payload = [
            'id' => 42,
            'type' => 'ALERT',
            'message' => 'Новый алерт',
        ];

        $event = new AlertCreated($payload);

        $this->assertSame('private-hydro.alerts', $event->broadcastOn()->name);
        $this->assertSame($payload, $event->alert);
    }

    public function test_node_config_updated_contains_device_snapshot(): void
    {
        $zone = $this->makeZone(7);
        $node = $this->makeDeviceNode(501, $zone->id);

        $event = new NodeConfigUpdated($node);

        $this->assertSame('private-hydro.devices', $event->broadcastOn()->name);
        $this->assertSame('device.updated', $event->broadcastAs());

        $payload = $event->broadcastWith();

        $this->assertSame($node->id, $payload['device']['id']);
        $this->assertSame($node->uid, $payload['device']['uid']);
        $this->assertSame($node->zone_id, $payload['device']['zone_id']);
        $this->assertArrayHasKey('status', $payload['device']);
        $this->assertArrayHasKey('was_recently_created', $payload['device']);
    }

    public function test_zone_updated_targets_private_zone_channel(): void
    {
        $zone = $this->makeZone(33, 'RUNNING', 'Delta');

        $event = new ZoneUpdated($zone);

        $this->assertSame("private-hydro.zones.{$zone->id}", $event->broadcastOn()->name);

        $payload = $event->broadcastWith();
        $this->assertSame($zone->id, $payload['zone']['id']);
        $this->assertSame($zone->name, $payload['zone']['name']);
        $this->assertSame($zone->status, $payload['zone']['status']);
    }

    public function test_command_status_updated_uses_zone_channel_when_zone_id_present(): void
    {
        $event = new CommandStatusUpdated(
            commandId: 501,
            status: 'queued',
            message: 'Ожидание исполнения',
            error: null,
            zoneId: 7,
        );

        $this->assertSame('private-commands.7', $event->broadcastOn()->name);

        $this->assertSame([
            'commandId' => 501,
            'status' => 'queued',
            'message' => 'Ожидание исполнения',
            'error' => null,
            'zoneId' => 7,
        ], $event->broadcastWith());
    }

    public function test_command_status_updated_falls_back_to_global_channel(): void
    {
        $event = new CommandStatusUpdated(
            commandId: 777,
            status: 'completed',
            message: 'Команда завершена',
        );

        $this->assertSame('private-commands.global', $event->broadcastOn()->name);
        $this->assertNull($event->broadcastWith()['zoneId']);
    }

    public function test_command_failed_broadcasts_to_zone_channel_when_zone_id_provided(): void
    {
        $event = new CommandFailed(
            commandId: 321,
            message: 'Ошибка выполнения',
            error: 'Timeout',
            zoneId: 12,
        );

        $this->assertSame('private-commands.12', $event->broadcastOn()->name);

        $this->assertSame([
            'commandId' => 321,
            'status' => Command::STATUS_FAILED,
            'message' => 'Ошибка выполнения',
            'error' => 'Timeout',
            'zoneId' => 12,
        ], $event->broadcastWith());
    }

    public function test_command_failed_uses_global_channel_without_zone(): void
    {
        $event = new CommandFailed(
            commandId: 654,
            message: 'Ошибка без зоны',
        );

        $this->assertSame('private-commands.global', $event->broadcastOn()->name);
        $this->assertNull($event->broadcastWith()['zoneId']);
    }

    public function test_event_created_uses_global_channel_and_defaults_timestamp(): void
    {
        Carbon::setTestNow('2024-02-10 10:00:00');

        $event = new EventCreated(
            id: 1001,
            kind: 'INFO',
            message: 'Событие создано',
        );

        $this->assertSame('private-events.global', $event->broadcastOn()->name);
        $this->assertSame('EventCreated', $event->broadcastAs());

        $payload = $event->broadcastWith();

        $this->assertSame(1001, $payload['id']);
        $this->assertSame('INFO', $payload['kind']);
        $this->assertSame('Событие создано', $payload['message']);
        $this->assertNull($payload['zoneId']);
        $this->assertSame(Carbon::now()->toIso8601String(), $payload['occurredAt']);

        Carbon::setTestNow();
    }
}
