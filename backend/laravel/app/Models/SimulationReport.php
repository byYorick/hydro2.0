<?php

namespace App\Models;

use Illuminate\Database\Eloquent\Factories\HasFactory;
use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\Relations\BelongsTo;

class SimulationReport extends Model
{
    use HasFactory;

    protected $fillable = [
        'simulation_id',
        'zone_id',
        'status',
        'started_at',
        'finished_at',
        'summary_json',
        'phases_json',
        'metrics_json',
        'errors_json',
    ];

    protected $casts = [
        'summary_json' => 'array',
        'phases_json' => 'array',
        'metrics_json' => 'array',
        'errors_json' => 'array',
        'started_at' => 'datetime',
        'finished_at' => 'datetime',
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
