<?php

namespace App\Models;

use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\Factories\HasFactory;
use Illuminate\Database\Eloquent\Relations\BelongsTo;

class Alert extends Model
{
    use HasFactory;

    public $timestamps = false;

    protected $fillable = [
        'zone_id',
        'source',
        'code',
        'type',
        'details',
        'status',
        'category',
        'severity',
        'node_uid',
        'hardware_id',
        'error_count',
        'first_seen_at',
        'last_seen_at',
        'created_at',
        'resolved_at',
    ];

    protected $casts = [
        'details' => 'array',
        'created_at' => 'datetime',
        'resolved_at' => 'datetime',
        'first_seen_at' => 'datetime',
        'last_seen_at' => 'datetime',
    ];

    public function zone(): BelongsTo
    {
        return $this->belongsTo(Zone::class);
    }
}

