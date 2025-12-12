<?php

namespace Tests\Unit\Events;

use App\Events\CommandStatusUpdated;
use Illuminate\Broadcasting\PrivateChannel;
use Tests\TestCase;

class CommandStatusUpdatedTest extends TestCase
{
    public function test_broadcasts_to_zone_channel_when_zone_id_provided(): void
    {
        $event = new CommandStatusUpdated(
            commandId: 42,
            status: 'completed',
            message: 'OK',
            error: null,
            zoneId: 7
        );

        $this->assertEquals(new PrivateChannel('commands.7'), $event->broadcastOn());
        $this->assertSame('CommandStatusUpdated', $event->broadcastAs());
        
        $data = $event->broadcastWith();
        $this->assertEquals(42, $data['commandId']);
        $this->assertEquals('completed', $data['status']);
        $this->assertEquals('OK', $data['message']);
        $this->assertNull($data['error']);
        $this->assertEquals(7, $data['zoneId']);
        // Проверяем наличие новых полей для reconciliation
        $this->assertArrayHasKey('event_id', $data);
        $this->assertArrayHasKey('server_ts', $data);
        $this->assertIsInt($data['event_id']);
        $this->assertIsInt($data['server_ts']);
    }

    public function test_falls_back_to_global_channel_when_zone_id_missing(): void
    {
        $event = new CommandStatusUpdated(
            commandId: 'cmd-1',
            status: 'failed',
            message: null,
            error: 'Timeout',
            zoneId: null
        );

        $this->assertEquals(new PrivateChannel('commands.global'), $event->broadcastOn());
        
        $data = $event->broadcastWith();
        $this->assertEquals('cmd-1', $data['commandId']);
        $this->assertEquals('failed', $data['status']);
        $this->assertNull($data['message']);
        $this->assertEquals('Timeout', $data['error']);
        $this->assertNull($data['zoneId']);
        // Проверяем наличие новых полей для reconciliation
        $this->assertArrayHasKey('event_id', $data);
        $this->assertArrayHasKey('server_ts', $data);
        $this->assertIsInt($data['event_id']);
        $this->assertIsInt($data['server_ts']);
    }
}
