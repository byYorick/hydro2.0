<?php

namespace App\Http\Resources;

use Illuminate\Http\Request;
use Illuminate\Http\Resources\Json\JsonResource;

class ZoneResource extends JsonResource
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
            'greenhouse_id' => $this->greenhouse_id,
            'preset_id' => $this->preset_id,
            'name' => $this->name,
            'description' => $this->description,
            'status' => $this->status,
            'health_score' => $this->health_score,
            'health_status' => $this->health_status,
            'hardware_profile' => $this->hardware_profile,
            'capabilities' => $this->capabilities,
            'water_state' => $this->water_state,
            'solution_started_at' => $this->solution_started_at?->toIso8601String(),
            'settings' => $this->settings,
            'created_at' => $this->created_at?->toIso8601String(),
            'updated_at' => $this->updated_at?->toIso8601String(),
            
            // Relationships
            'greenhouse' => $this->whenLoaded('greenhouse', function () {
                return [
                    'id' => $this->greenhouse->id,
                    'uid' => $this->greenhouse->uid,
                    'name' => $this->greenhouse->name,
                ];
            }),
            'preset' => $this->whenLoaded('preset', function () {
                return [
                    'id' => $this->preset->id,
                    'name' => $this->preset->name,
                ];
            }),
            'nodes' => NodeResource::collection($this->whenLoaded('nodes')),
            'recipe_instance' => $this->whenLoaded('recipeInstance', function () {
                return [
                    'id' => $this->recipeInstance->id,
                    'recipe_id' => $this->recipeInstance->recipe_id,
                    'current_phase_id' => $this->recipeInstance->current_phase_id,
                ];
            }),
        ];
    }
}

