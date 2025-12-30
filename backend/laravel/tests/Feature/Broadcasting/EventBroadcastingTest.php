<?php

namespace Tests\Feature\Broadcasting;

use App\Events\AlertCreated;
use App\Events\CommandFailed;
use App\Events\CommandStatusUpdated;
use App\Events\EventCreated;
use App\Events\NodeConfigUpdated;
use App\Events\TelemetryBatchUpdated;
use App\Events\ZoneUpdated;
use App\Models\DeviceNode;
use App\Models\Greenhouse;
use App\Models\User;
use App\Models\Zone;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Illuminate\Support\Facades\Event;
use Illuminate\Support\Facades\Log;
use Tests\TestCase;

class EventBroadcastingTest extends TestCase
{
    use RefreshDatabase;

    protected function setUp(): void
    {
        parent::setUp();
        // В тестах мы используем Event::fake() для проверки, что события отправляются
        // Но мы можем использовать реальное broadcasting для проверки структуры
    }

    /**
     * Тест broadcasting события обновления статуса команды с зоной
     */
    public function test_command_status_updated_broadcasts_to_zone_channel(): void
    {
        Event::fake();

        $event = new CommandStatusUpdated(
            commandId: 101,
            status: 'completed',
            message: 'Команда выполнена',
            error: null,
            zoneId: 5
        );

        event($event);

        Event::assertDispatched(CommandStatusUpdated::class, function ($e) {
            return $e->commandId === 101
                && $e->status === 'completed'
                && $e->zoneId === 5
                && $e->broadcastOn()->name === 'private-commands.5';
        });
    }

    /**
     * Тест broadcasting события обновления статуса команды без зоны (глобальный канал)
     */
    public function test_command_status_updated_broadcasts_to_global_channel(): void
    {
        Event::fake();

        $event = new CommandStatusUpdated(
            commandId: 202,
            status: 'failed',
            message: null,
            error: 'Timeout',
            zoneId: null
        );

        event($event);

        Event::assertDispatched(CommandStatusUpdated::class, function ($e) {
            return $e->commandId === 202
                && $e->broadcastOn()->name === 'private-commands.global';
        });
    }

    /**
     * Тест broadcasting события обновления зоны
     */
    public function test_zone_updated_broadcasts(): void
    {
        Event::fake();

        $greenhouse = Greenhouse::factory()->create();
        $zone = Zone::factory()->create([
            'greenhouse_id' => $greenhouse->id,
            'name' => 'Test Zone',
            'status' => 'RUNNING',
        ]);

        $event = new ZoneUpdated($zone);

        event($event);

        Event::assertDispatched(ZoneUpdated::class, function ($e) use ($zone) {
            return $e->zone->id === $zone->id
                && $e->broadcastOn()->name === "private-hydro.zones.{$zone->id}";
        });
    }

    /**
     * Тест broadcasting события создания алерта
     */
    public function test_alert_created_broadcasts(): void
    {
        Event::fake();

        $alert = [
            'id' => 42,
            'type' => 'ALERT',
            'message' => 'Новый алерт',
        ];

        $event = new AlertCreated($alert);

        event($event);

        Event::assertDispatched(AlertCreated::class, function ($e) use ($alert) {
            return $e->alert['id'] === $alert['id']
                && $e->broadcastOn()->name === 'private-hydro.alerts';
        });
    }

    /**
     * Тест broadcasting события обновления конфигурации узла
     */
    public function test_node_config_updated_broadcasts(): void
    {
        Event::fake();

        $greenhouse = Greenhouse::factory()->create();
        $zone = Zone::factory()->create(['greenhouse_id' => $greenhouse->id]);
        $node = DeviceNode::factory()->create(['zone_id' => $zone->id]);

        $event = new NodeConfigUpdated($node);

        event($event);

        Event::assertDispatched(NodeConfigUpdated::class, function ($e) use ($node) {
            return $e->node->id === $node->id
                && $e->broadcastOn()->name === "private-hydro.zones.{$node->zone_id}";
        });
    }

    public function test_telemetry_batch_updated_broadcasts(): void
    {
        Event::fake();

        $event = new TelemetryBatchUpdated(12, [[
            'node_id' => 501,
            'channel' => 'ec_sensor',
            'metric_type' => 'EC',
            'value' => 1.4,
            'ts' => 1700000000000,
        ]]);

        event($event);

        Event::assertDispatched(TelemetryBatchUpdated::class, function ($e) {
            return $e->broadcastOn()->name === 'private-hydro.zones.12'
                && $e->broadcastAs() === 'telemetry.batch.updated';
        });
    }

    /**
     * Тест broadcasting события неудачной команды
     */
    public function test_command_failed_broadcasts(): void
    {
        Event::fake();

        $event = new CommandFailed(
            commandId: 303,
            message: 'Ошибка выполнения',
            error: 'Connection timeout',
            zoneId: 7
        );

        event($event);

        Event::assertDispatched(CommandFailed::class, function ($e) {
            return $e->commandId === 303
                && $e->error === 'Connection timeout'
                && $e->zoneId === 7
                && $e->broadcastOn()->name === 'private-commands.7';
        });
    }

    /**
     * Тест broadcasting события создания события
     */
    public function test_event_created_broadcasts(): void
    {
        Event::fake();

        $event = new EventCreated(
            id: 1001,
            kind: 'INFO',
            message: 'Событие создано'
        );

        event($event);

        Event::assertDispatched(EventCreated::class, function ($e) {
            return $e->id === 1001
                && $e->broadcastOn()->name === 'private-events.global';
        });
    }

    /**
     * Тест структуры данных для broadcasting события команды
     */
    public function test_command_status_updated_broadcast_with_data(): void
    {
        $event = new CommandStatusUpdated(
            commandId: 404,
            status: 'queued',
            message: 'Ожидание выполнения',
            error: null,
            zoneId: 15
        );

        $data = $event->broadcastWith();

        $this->assertEquals(404, $data['commandId']);
        $this->assertEquals('queued', $data['status']);
        $this->assertEquals('Ожидание выполнения', $data['message']);
        $this->assertNull($data['error']);
        $this->assertEquals(15, $data['zoneId']);
    }

    /**
     * Тест структуры данных для broadcasting события зоны
     */
    public function test_zone_updated_broadcast_with_data(): void
    {
        $greenhouse = Greenhouse::factory()->create();
        $zone = Zone::factory()->create([
            'greenhouse_id' => $greenhouse->id,
            'name' => 'Test Zone Updated',
            'status' => 'PAUSED',
        ]);

        $event = new ZoneUpdated($zone);

        $data = $event->broadcastWith();

        $this->assertEquals($zone->id, $data['zone']['id']);
        $this->assertEquals('Test Zone Updated', $data['zone']['name']);
        $this->assertEquals('PAUSED', $data['zone']['status']);
    }
}
