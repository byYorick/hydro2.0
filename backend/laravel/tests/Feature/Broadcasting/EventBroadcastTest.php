<?php

namespace Tests\Feature\Broadcasting;

use App\Events\AlertCreated;
use App\Events\CommandFailed;
use App\Events\CommandStatusUpdated;
use App\Events\EventCreated;
use App\Events\NodeConfigUpdated;
use App\Events\TelemetryBatchUpdated;
use App\Events\ZoneUpdated;
use App\Models\Command;
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

        $this->assertSame("private-hydro.zones.{$zone->id}", $event->broadcastOn()->name);
        $this->assertSame('device.updated', $event->broadcastAs());

        $payload = $event->broadcastWith();

        $this->assertSame($node->id, $payload['device']['id']);
        $this->assertSame($node->uid, $payload['device']['uid']);
        $this->assertSame($node->zone_id, $payload['device']['zone_id']);
        $this->assertArrayHasKey('status', $payload['device']);
        $this->assertArrayHasKey('was_recently_created', $payload['device']);
    }

    public function test_telemetry_batch_updated_targets_zone_channel(): void
    {
        $event = new TelemetryBatchUpdated(9, [[
            'node_id' => 501,
            'channel' => 'ph_sensor',
            'metric_type' => 'PH',
            'value' => 6.1,
            'ts' => 1700000000000,
        ]]);

        $this->assertSame('private-hydro.zones.9', $event->broadcastOn()->name);
        $this->assertSame('telemetry.batch.updated', $event->broadcastAs());

        $payload = $event->broadcastWith();
        $this->assertSame(9, $payload['zone_id']);
        $this->assertCount(1, $payload['updates']);
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
        $payload = $event->broadcastWith();
        $this->assertSame(501, $payload['commandId']);
        $this->assertSame('QUEUED', $payload['status']);
        $this->assertSame('Ожидание исполнения', $payload['message']);
        $this->assertNull($payload['error']);
        $this->assertSame(7, $payload['zoneId']);
        $this->assertArrayHasKey('event_id', $payload);
        $this->assertArrayHasKey('server_ts', $payload);
    }

    public function test_command_status_updated_falls_back_to_global_channel(): void
    {
        $event = new CommandStatusUpdated(
            commandId: 777,
            status: 'DONE',
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
            status: Command::STATUS_ERROR,
            zoneId: 12,
        );

        $this->assertSame('private-commands.12', $event->broadcastOn()->name);
        $payload = $event->broadcastWith();
        $this->assertSame(321, $payload['commandId']);
        $this->assertSame(Command::STATUS_ERROR, $payload['status']);
        $this->assertSame('Ошибка выполнения', $payload['message']);
        $this->assertSame('Timeout', $payload['error']);
        $this->assertSame(12, $payload['zoneId']);
        $this->assertArrayHasKey('event_id', $payload);
        $this->assertArrayHasKey('server_ts', $payload);
    }

    public function test_command_failed_uses_global_channel_without_zone(): void
    {
        $event = new CommandFailed(
            commandId: 654,
            message: 'Ошибка без зоны',
            status: Command::STATUS_ERROR,
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
