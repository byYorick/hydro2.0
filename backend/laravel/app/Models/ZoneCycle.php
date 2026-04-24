<?php

namespace App\Models;

use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\Relations\BelongsTo;

class ZoneCycle extends Model
{
    protected $table = 'zone_cycles';

    protected $fillable = [
        'zone_id',
        'type',
        'status',
        'subsystems',
        'started_at',
        'ends_at',
    ];

    protected $casts = [
        'subsystems' => 'array',
        'started_at' => 'immutable_datetime',
        'ends_at' => 'immutable_datetime',
    ];

    public function zone(): BelongsTo
    {
        return $this->belongsTo(Zone::class);
    }
}



