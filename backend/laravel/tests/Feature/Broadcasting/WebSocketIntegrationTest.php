<?php

namespace Tests\Feature\Broadcasting;

use App\Events\CommandStatusUpdated;
use App\Events\ZoneUpdated;
use App\Models\Greenhouse;
use App\Models\User;
use App\Models\Zone;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Illuminate\Support\Facades\Event;
use Illuminate\Support\Facades\Log;
use Tests\TestCase;

class WebSocketIntegrationTest extends TestCase
{
    use RefreshDatabase;

    /**
     * Тест полного цикла broadcasting события команды
     */
    public function test_command_status_broadcasting_flow(): void
    {
        Event::fake();

        $event = new CommandStatusUpdated(
            commandId: 501,
            status: 'completed',
            message: 'Успешно выполнено',
            error: null,
            zoneId: 10
        );

        // Отправляем событие
        event($event);

        // Проверяем, что событие было отправлено
        Event::assertDispatched(CommandStatusUpdated::class, function ($e) {
            return $e->commandId === 501
                && $e->status === 'completed'
                && $e->broadcastOn()->name === 'private-commands.10';
        });

        // Проверяем данные для broadcasting
        $broadcastData = $event->broadcastWith();
        $this->assertEquals('completed', $broadcastData['status']);
        $this->assertEquals('Успешно выполнено', $broadcastData['message']);
        $this->assertEquals(10, $broadcastData['zoneId']);
    }

    /**
     * Тест broadcasting нескольких событий подряд
     */
    public function test_multiple_events_broadcasting(): void
    {
        Event::fake();

        $greenhouse = Greenhouse::factory()->create();
        $zone1 = Zone::factory()->create(['greenhouse_id' => $greenhouse->id]);
        $zone2 = Zone::factory()->create(['greenhouse_id' => $greenhouse->id]);

        // Отправляем несколько событий
        event(new CommandStatusUpdated(1, 'queued', null, null, $zone1->id));
        event(new CommandStatusUpdated(2, 'processing', null, null, $zone1->id));
        event(new CommandStatusUpdated(3, 'completed', 'Done', null, $zone2->id));
        event(new ZoneUpdated($zone1));
        event(new ZoneUpdated($zone2));

        // Проверяем, что все события были отправлены
        Event::assertDispatched(CommandStatusUpdated::class, 3);
        Event::assertDispatched(ZoneUpdated::class, 2);
    }

    /**
     * Тест broadcasting событий с разными статусами команды
     */
    public function test_command_events_with_different_statuses(): void
    {
        Event::fake();

        $statuses = ['queued', 'processing', 'completed', 'failed'];

        foreach ($statuses as $index => $status) {
            $event = new CommandStatusUpdated(
                commandId: 100 + $index,
                status: $status,
                message: "Status: {$status}",
                error: $status === 'failed' ? 'Error occurred' : null,
                zoneId: 5
            );

            event($event);

            Event::assertDispatched(CommandStatusUpdated::class, function ($e) use ($status) {
                return $e->status === $status;
            });
        }
    }

    /**
     * Тест broadcasting событий для разных зон
     */
    public function test_broadcasting_to_different_zones(): void
    {
        Event::fake();

        $greenhouse = Greenhouse::factory()->create();
        $zones = Zone::factory()->count(5)->create(['greenhouse_id' => $greenhouse->id]);

        foreach ($zones as $zone) {
            $event = new CommandStatusUpdated(
                commandId: $zone->id * 10,
                status: 'completed',
                message: "Zone {$zone->id} updated",
                error: null,
                zoneId: $zone->id
            );

            event($event);

            Event::assertDispatched(CommandStatusUpdated::class, function ($e) use ($zone) {
                return $e->zoneId === $zone->id
                    && $e->broadcastOn()->name === "private-commands.{$zone->id}";
            });
        }
    }

    /**
     * Тест broadcasting события без зоны (глобальный канал)
     */
    public function test_global_command_broadcasting(): void
    {
        Event::fake();

        $event = new CommandStatusUpdated(
            commandId: 999,
            status: 'failed',
            message: 'Global error',
            error: 'System error',
            zoneId: null
        );

        event($event);

        Event::assertDispatched(CommandStatusUpdated::class, function ($e) {
            return $e->commandId === 999
                && $e->zoneId === null
                && $e->broadcastOn()->name === 'private-commands.global';
        });
    }

    /**
     * Тест имен событий для broadcasting
     */
    public function test_broadcast_event_names(): void
    {
        $commandEvent = new CommandStatusUpdated(1, 'completed', null, null, 1);
        $this->assertEquals('CommandStatusUpdated', $commandEvent->broadcastAs());

        $greenhouse = Greenhouse::factory()->create();
        $zone = Zone::factory()->create(['greenhouse_id' => $greenhouse->id]);
        $zoneEvent = new ZoneUpdated($zone);
        
        // ZoneUpdated может не иметь broadcastAs(), используем имя класса
        $this->assertInstanceOf(\Illuminate\Contracts\Broadcasting\ShouldBroadcast::class, $zoneEvent);
    }

    /**
     * Тест очереди для broadcasting событий
     */
    public function test_broadcasting_events_use_broadcasts_queue(): void
    {
        $commandEvent = new CommandStatusUpdated(1, 'completed', null, null, 1);
        $this->assertEquals('broadcasts', $commandEvent->queue);

        $greenhouse = Greenhouse::factory()->create();
        $zone = Zone::factory()->create(['greenhouse_id' => $greenhouse->id]);
        $zoneEvent = new ZoneUpdated($zone);
        $this->assertEquals('broadcasts', $zoneEvent->queue);
    }
}

