<?php

namespace App\Models;

use App\Enums\GrowCycleStatus;
use Illuminate\Database\Eloquent\Factories\HasFactory;
use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\Relations\BelongsTo;

class GrowCycle extends Model
{
    use HasFactory;

    protected $fillable = [
        'greenhouse_id',
        'zone_id',
        'plant_id',
        'recipe_id',
        'zone_recipe_instance_id',
        'status',
        'started_at',
        'recipe_started_at',
        'expected_harvest_at',
        'actual_harvest_at',
        'batch_label',
        'notes',
        'settings',
        'current_stage_code',
        'current_stage_started_at',
        'planting_at',
    ];

    protected $casts = [
        'status' => GrowCycleStatus::class,
        'started_at' => 'datetime',
        'recipe_started_at' => 'datetime',
        'expected_harvest_at' => 'datetime',
        'actual_harvest_at' => 'datetime',
        'current_stage_started_at' => 'datetime',
        'planting_at' => 'datetime',
        'settings' => 'array',
    ];

    public function greenhouse(): BelongsTo
    {
        return $this->belongsTo(Greenhouse::class);
    }

    public function zone(): BelongsTo
    {
        return $this->belongsTo(Zone::class);
    }

    public function plant(): BelongsTo
    {
        return $this->belongsTo(Plant::class);
    }

    public function recipe(): BelongsTo
    {
        return $this->belongsTo(Recipe::class);
    }

    public function zoneRecipeInstance(): BelongsTo
    {
        return $this->belongsTo(ZoneRecipeInstance::class);
    }
}

