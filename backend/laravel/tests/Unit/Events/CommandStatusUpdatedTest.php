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
        $this->assertEquals([
            'commandId' => 42,
            'status' => 'completed',
            'message' => 'OK',
            'error' => null,
            'zoneId' => 7,
        ], $event->broadcastWith());
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
        $this->assertEquals([
            'commandId' => 'cmd-1',
            'status' => 'failed',
            'message' => null,
            'error' => 'Timeout',
            'zoneId' => null,
        ], $event->broadcastWith());
    }
}
