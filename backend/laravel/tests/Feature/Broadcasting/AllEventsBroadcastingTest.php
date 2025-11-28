<?php

namespace Tests\Feature\Broadcasting;

use App\Events\AlertCreated;
use App\Events\CommandFailed;
use App\Events\CommandStatusUpdated;
use App\Events\EventCreated;
use App\Events\NodeConfigUpdated;
use App\Events\ZoneUpdated;
use App\Models\DeviceNode;
use App\Models\Greenhouse;
use App\Models\Zone;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Illuminate\Support\Facades\Event;
use Tests\TestCase;

class AllEventsBroadcastingTest extends TestCase
{
    use RefreshDatabase;

    /**
     * Тест всех событий broadcasting на правильные каналы
     */
    public function test_all_events_broadcast_to_correct_channels(): void
    {
        Event::fake();

        $greenhouse = Greenhouse::factory()->create();
        $zone = Zone::factory()->create(['greenhouse_id' => $greenhouse->id]);
        $node = DeviceNode::factory()->create(['zone_id' => $zone->id]);

        // CommandStatusUpdated - канал команд зоны
        event(new CommandStatusUpdated(1, 'completed', null, null, $zone->id));
        Event::assertDispatched(CommandStatusUpdated::class, function ($e) use ($zone) {
            return $e->broadcastOn()->name === "private-commands.{$zone->id}";
        });

        // CommandStatusUpdated - глобальный канал команд
        event(new CommandStatusUpdated(2, 'failed', null, 'Error', null));
        Event::assertDispatched(CommandStatusUpdated::class, function ($e) {
            return $e->broadcastOn()->name === 'private-commands.global';
        });

        // CommandFailed - канал команд зоны
        event(new CommandFailed(3, 'Failed', 'Error', $zone->id));
        Event::assertDispatched(CommandFailed::class, function ($e) use ($zone) {
            return $e->broadcastOn()->name === "private-commands.{$zone->id}";
        });

        // ZoneUpdated - канал зоны
        event(new ZoneUpdated($zone));
        Event::assertDispatched(ZoneUpdated::class, function ($e) use ($zone) {
            return $e->broadcastOn()->name === "private-hydro.zones.{$zone->id}";
        });

        // NodeConfigUpdated - канал устройств
        event(new NodeConfigUpdated($node));
        Event::assertDispatched(NodeConfigUpdated::class, function ($e) {
            return $e->broadcastOn()->name === 'private-hydro.devices';
        });

        // AlertCreated - канал алертов
        event(new AlertCreated(['id' => 1, 'type' => 'ALERT', 'message' => 'Test']));
        Event::assertDispatched(AlertCreated::class, function ($e) {
            return $e->broadcastOn()->name === 'private-hydro.alerts';
        });

        // EventCreated - глобальный канал событий
        event(new EventCreated(1, 'INFO', 'Test event'));
        Event::assertDispatched(EventCreated::class, function ($e) {
            return $e->broadcastOn()->name === 'private-events.global';
        });
    }

    /**
     * Тест структуры данных всех событий
     */
    public function test_all_events_have_correct_broadcast_data(): void
    {
        $greenhouse = Greenhouse::factory()->create();
        $zone = Zone::factory()->create([
            'greenhouse_id' => $greenhouse->id,
            'name' => 'Test Zone',
            'status' => 'RUNNING',
        ]);
        $node = DeviceNode::factory()->create(['zone_id' => $zone->id]);

        // CommandStatusUpdated
        $commandEvent = new CommandStatusUpdated(100, 'completed', 'Done', null, $zone->id);
        $commandData = $commandEvent->broadcastWith();
        $this->assertEquals(100, $commandData['commandId']);
        $this->assertEquals('completed', $commandData['status']);
        $this->assertEquals($zone->id, $commandData['zoneId']);

        // CommandFailed
        $failedEvent = new CommandFailed(200, 'Failed', 'Error', $zone->id);
        $failedData = $failedEvent->broadcastWith();
        $this->assertEquals(200, $failedData['commandId']);
        $this->assertEquals('failed', $failedData['status']);
        $this->assertEquals('Error', $failedData['error']);

        // ZoneUpdated
        $zoneEvent = new ZoneUpdated($zone);
        $zoneData = $zoneEvent->broadcastWith();
        $this->assertEquals($zone->id, $zoneData['zone']['id']);
        $this->assertEquals('Test Zone', $zoneData['zone']['name']);
        $this->assertEquals('RUNNING', $zoneData['zone']['status']);

        // NodeConfigUpdated
        $nodeEvent = new NodeConfigUpdated($node);
        $nodeData = $nodeEvent->broadcastWith();
        $this->assertArrayHasKey('device', $nodeData);
        $this->assertEquals($node->id, $nodeData['device']['id']);

        // AlertCreated
        $alertEvent = new AlertCreated(['id' => 1, 'type' => 'ALERT']);
        $this->assertEquals(['id' => 1, 'type' => 'ALERT'], $alertEvent->alert);

        // EventCreated
        $eventCreated = new EventCreated(1, 'INFO', 'Test');
        $eventData = $eventCreated->broadcastWith();
        $this->assertEquals(1, $eventData['id']);
        $this->assertEquals('INFO', $eventData['kind']);
        $this->assertEquals('Test', $eventData['message']);
    }

    /**
     * Тест имен событий для broadcasting
     */
    public function test_all_events_have_broadcast_names(): void
    {
        $commandEvent = new CommandStatusUpdated(1, 'completed', null, null, 1);
        $this->assertEquals('CommandStatusUpdated', $commandEvent->broadcastAs());

        $greenhouse = Greenhouse::factory()->create();
        $zone = Zone::factory()->create(['greenhouse_id' => $greenhouse->id]);
        
        $failedEvent = new CommandFailed(1, 'Failed', 'Error', $zone->id);
        $this->assertEquals('CommandFailed', $failedEvent->broadcastAs());

        $eventCreated = new EventCreated(1, 'INFO', 'Test');
        $this->assertEquals('EventCreated', $eventCreated->broadcastAs());
    }
}

