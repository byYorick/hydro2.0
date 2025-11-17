<?php

namespace App\Models;

use Illuminate\Database\Eloquent\Factories\HasFactory;
use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\Relations\BelongsTo;

class NodeChannel extends Model
{
    use HasFactory;

    protected $fillable = [
        'node_id',
        'channel',
        'type',
        'metric',
        'unit',
        'config',
    ];

    protected $casts = [
        'config' => 'array',
    ];

    public function node(): BelongsTo
    {
        return $this->belongsTo(DeviceNode::class, 'node_id');
    }
}


