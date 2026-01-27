<?php

namespace App\Models;

use Illuminate\Database\Eloquent\Factories\HasFactory;
use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\Relations\BelongsTo;

class SimulationEvent extends Model
{
    use HasFactory;

    public $timestamps = false;

    protected $fillable = [
        'simulation_id',
        'zone_id',
        'service',
        'stage',
        'status',
        'level',
        'message',
        'payload',
        'occurred_at',
        'created_at',
    ];

    protected $casts = [
        'payload' => 'array',
        'occurred_at' => 'datetime',
        'created_at' => 'datetime',
    ];

    public function simulation(): BelongsTo
    {
        return $this->belongsTo(ZoneSimulation::class, 'simulation_id');
    }

    public function zone(): BelongsTo
    {
        return $this->belongsTo(Zone::class);
    }
}
