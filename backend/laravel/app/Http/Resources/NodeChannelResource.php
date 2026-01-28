<?php

namespace App\Http\Resources;

use Illuminate\Http\Request;
use Illuminate\Http\Resources\Json\JsonResource;

class NodeChannelResource extends JsonResource
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
            'node_id' => $this->node_id,
            'channel' => $this->channel,
            'type' => $this->type,
            'metric' => $this->metric,
            'unit' => $this->unit,
            // config НЕ включается для безопасности (защита параметров актуаторов)
        ];
    }
}
