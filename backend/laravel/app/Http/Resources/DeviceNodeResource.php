<?php

namespace App\Http\Resources;

use Illuminate\Http\Request;
use Illuminate\Http\Resources\Json\JsonResource;

class DeviceNodeResource extends JsonResource
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
            'zone_id' => $this->zone_id,
            'pending_zone_id' => $this->pending_zone_id,
            'uid' => $this->uid,
            'name' => $this->name,
            'type' => $this->type,
            'fw_version' => $this->fw_version,
            'hardware_revision' => $this->hardware_revision,
            'hardware_id' => $this->hardware_id,
            'last_seen_at' => $this->last_seen_at?->toIso8601String(),
            'last_heartbeat_at' => $this->last_heartbeat_at?->toIso8601String(),
            'first_seen_at' => $this->first_seen_at?->toIso8601String(),
            'status' => $this->status,
            'lifecycle_state' => $this->lifecycle_state?->value,
            'validated' => $this->validated,
            'uptime_seconds' => $this->uptime_seconds,
            'free_heap_bytes' => $this->free_heap_bytes,
            'rssi' => $this->rssi,
            // config НЕ включается для безопасности (защита Wi-Fi паролей и MQTT кредов)
            'channels' => NodeChannelResource::collection($this->whenLoaded('channels')),
            'zone' => $this->whenLoaded('zone', function () {
                return [
                    'id' => $this->zone->id,
                    'name' => $this->zone->name,
                    'status' => $this->zone->status,
                ];
            }),
        ];
    }
}
