<?php

namespace App\Models;

use Illuminate\Database\Eloquent\Factories\HasFactory;
use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\Relations\BelongsTo;

class CommandsArchive extends Model
{
    use HasFactory;

    protected $table = 'commands_archive';

    public $timestamps = false;

    protected $fillable = [
        'zone_id',
        'node_id',
        'channel',
        'cmd',
        'params',
        'status',
        'cmd_id',
        'created_at',
        'sent_at',
        'ack_at',
        'failed_at',
        'archived_at',
    ];

    protected $casts = [
        'params' => 'array',
        'created_at' => 'datetime',
        'sent_at' => 'datetime',
        'ack_at' => 'datetime',
        'failed_at' => 'datetime',
        'archived_at' => 'datetime',
    ];

    public function zone(): BelongsTo
    {
        return $this->belongsTo(Zone::class);
    }

    public function node(): BelongsTo
    {
        return $this->belongsTo(DeviceNode::class, 'node_id');
    }
}

