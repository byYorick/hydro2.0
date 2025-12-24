<?php

namespace App\Models;

use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\Factories\HasFactory;
use Illuminate\Database\Eloquent\Relations\BelongsTo;

class UnassignedNodeError extends Model
{
    use HasFactory;

    protected $fillable = [
        'hardware_id',
        'error_message',
        'error_code',
        'severity',
        'topic',
        'last_payload',
        'count',
        'first_seen_at',
        'last_seen_at',
        'node_id',
    ];

    protected $casts = [
        'last_payload' => 'array',
        'first_seen_at' => 'datetime',
        'last_seen_at' => 'datetime',
    ];

    public function node(): BelongsTo
    {
        return $this->belongsTo(DeviceNode::class, 'node_id');
    }
}

