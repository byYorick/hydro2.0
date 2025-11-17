<?php

namespace App\Models;

use Illuminate\Database\Eloquent\Factories\HasFactory;
use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\Relations\BelongsTo;

class ZoneSimulation extends Model
{
    use HasFactory;

    protected $fillable = [
        'zone_id',
        'scenario',
        'results',
        'duration_hours',
        'step_minutes',
        'status',
        'error_message',
    ];

    protected $casts = [
        'scenario' => 'array',
        'results' => 'array',
        'duration_hours' => 'integer',
        'step_minutes' => 'integer',
    ];

    public function zone(): BelongsTo
    {
        return $this->belongsTo(Zone::class);
    }
}
