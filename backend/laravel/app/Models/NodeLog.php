<?php

namespace App\Models;

use Illuminate\Database\Eloquent\Factories\HasFactory;
use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\Relations\BelongsTo;

class NodeLog extends Model
{
    use HasFactory;

    public $timestamps = false;

    protected $fillable = [
        'node_id',
        'level',
        'message',
        'context',
    ];

    protected $casts = [
        'context' => 'array',
        'created_at' => 'datetime',
    ];

    public function node(): BelongsTo
    {
        return $this->belongsTo(DeviceNode::class, 'node_id');
    }
}

