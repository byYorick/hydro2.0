<?php

namespace App\Models;

use Illuminate\Database\Eloquent\Factories\HasFactory;
use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\Relations\BelongsTo;

class PlantCycle extends Model
{
    use HasFactory;

    protected $fillable = [
        'plant_id',
        'cycle_id',
        'zone_id',
        'season',
        'settings',
        'metrics_snapshot',
    ];

    protected $casts = [
        'settings' => 'array',
        'metrics_snapshot' => 'array',
    ];

    public function plant(): BelongsTo
    {
        return $this->belongsTo(Plant::class);
    }

    public function zone(): BelongsTo
    {
        return $this->belongsTo(Zone::class);
    }
}
