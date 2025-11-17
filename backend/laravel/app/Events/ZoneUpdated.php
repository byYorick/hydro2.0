<?php

namespace App\Events;

use App\Models\Zone;
use Illuminate\Broadcasting\Channel;
use Illuminate\Broadcasting\InteractsWithSockets;
use Illuminate\Broadcasting\PresenceChannel;
use Illuminate\Broadcasting\PrivateChannel;
use Illuminate\Contracts\Broadcasting\ShouldBroadcast;
use Illuminate\Foundation\Events\Dispatchable;
use Illuminate\Queue\SerializesModels;

class ZoneUpdated implements ShouldBroadcast
{
    use Dispatchable, InteractsWithSockets, SerializesModels;

    public Zone $zone;

    public function __construct(Zone $zone)
    {
        $this->zone = $zone;
    }

    public function broadcastOn(): Channel
    {
        return new PrivateChannel("hydro.zones.{$this->zone->id}");
    }

    public function broadcastWith(): array
    {
        return [
            'zone' => [
                'id' => $this->zone->id,
                'name' => $this->zone->name,
                'status' => $this->zone->status,
            ],
        ];
    }
}

