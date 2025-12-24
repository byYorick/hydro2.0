<?php

namespace App\Http\Resources;

use Illuminate\Http\Request;
use Illuminate\Http\Resources\Json\JsonResource;

class NodeResource extends JsonResource
{
    /**
     * Transform the resource into an array.
     *
     * @return array<string, mixed>
     */
    public function toArray(Request $request): array
    {
        return [
            'id' => $this->id,
            'uid' => $this->uid,
            'name' => $this->name,
            'type' => $this->type,
            'zone_id' => $this->zone_id,
            'status' => $this->status,
            'lifecycle_state' => $this->lifecycle_state?->value,
            'fw_version' => $this->fw_version,
            'hardware_revision' => $this->hardware_revision,
            'hardware_id' => $this->hardware_id,
            'validated' => $this->validated,
            'first_seen_at' => $this->first_seen_at?->toIso8601String(),
            'last_seen_at' => $this->last_seen_at?->toIso8601String(),
            'last_heartbeat_at' => $this->last_heartbeat_at?->toIso8601String(),
            'uptime_seconds' => $this->uptime_seconds,
            'free_heap_bytes' => $this->free_heap_bytes,
            'rssi' => $this->rssi,
            'created_at' => $this->created_at?->toIso8601String(),
            'updated_at' => $this->updated_at?->toIso8601String(),
            
            // Relationships
            'zone' => $this->whenLoaded('zone', function () {
                return [
                    'id' => $this->zone->id,
                    'uid' => $this->zone->uid,
                    'name' => $this->zone->name,
                    'status' => $this->zone->status,
                ];
            }),
            'channels' => ChannelResource::collection($this->whenLoaded('channels')),
        ];
    }
}

