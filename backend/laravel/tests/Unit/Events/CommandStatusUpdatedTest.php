<?php

use App\Events\CommandStatusUpdated;
use Illuminate\Broadcasting\PrivateChannel;

it('broadcasts to zone channel when zone id provided', function () {
    $event = new CommandStatusUpdated(
        commandId: 42,
        status: 'completed',
        message: 'OK',
        error: null,
        zoneId: 7
    );

    expect($event->broadcastOn())->toEqual(new PrivateChannel('commands.7'))
        ->and($event->broadcastAs())->toBe('CommandStatusUpdated')
        ->and($event->broadcastWith())->toMatchArray([
            'commandId' => 42,
            'status' => 'completed',
            'message' => 'OK',
            'error' => null,
            'zoneId' => 7,
        ]);
});

it('falls back to global channel when zone id missing', function () {
    $event = new CommandStatusUpdated(
        commandId: 'cmd-1',
        status: 'failed',
        message: null,
        error: 'Timeout',
        zoneId: null
    );

    expect($event->broadcastOn())->toEqual(new PrivateChannel('commands.global'))
        ->and($event->broadcastWith())->toMatchArray([
            'zoneId' => null,
            'error' => 'Timeout',
        ]);
});
