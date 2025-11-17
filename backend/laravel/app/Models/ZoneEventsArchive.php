<?php

namespace App\Models;

use Illuminate\Database\Eloquent\Factories\HasFactory;
use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\Relations\BelongsTo;

class ZoneEventsArchive extends Model
{
    use HasFactory;

    protected $table = 'zone_events_archive';

    public $timestamps = false;

    protected $fillable = [
        'zone_id',
        'type',
        'details',
        'created_at',
        'archived_at',
    ];

    protected $casts = [
        'details' => 'array',
        'created_at' => 'datetime',
        'archived_at' => 'datetime',
    ];

    public function zone(): BelongsTo
    {
        return $this->belongsTo(Zone::class);
    }
}

