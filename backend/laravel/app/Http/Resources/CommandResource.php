<?php

namespace App\Http\Resources;

use Illuminate\Http\Request;
use Illuminate\Http\Resources\Json\JsonResource;

class CommandResource extends JsonResource
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
            'cmd_id' => $this->cmd_id,
            'zone_id' => $this->zone_id,
            'node_id' => $this->node_id,
            'channel' => $this->channel,
            'cmd' => $this->cmd,
            'params' => $this->params,
            'status' => $this->status,
            'error_message' => $this->error_message,
            'created_at' => $this->created_at?->toIso8601String(),
            'updated_at' => $this->updated_at?->toIso8601String(),
            
            // Relationships
            'zone' => $this->whenLoaded('zone', function () {
                return [
                    'id' => $this->zone->id,
                    'uid' => $this->zone->uid,
                    'name' => $this->zone->name,
                ];
            }),
            'node' => $this->whenLoaded('node', function () {
                return [
                    'id' => $this->node->id,
                    'uid' => $this->node->uid,
                    'name' => $this->node->name,
                ];
            }),
        ];
    }
}

