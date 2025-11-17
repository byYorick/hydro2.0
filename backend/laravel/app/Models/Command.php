<?php

namespace App\Models;

use Illuminate\Database\Eloquent\Factories\HasFactory;
use Illuminate\Database\Eloquent\Model;

class Command extends Model
{
    use HasFactory;

    protected $fillable = [
        'zone_id',
        'node_id',
        'channel',
        'cmd',
        'params',
        'status',
        'cmd_id',
        'sent_at',
        'ack_at',
        'failed_at',
    ];

    protected $casts = [
        'params' => 'array',
        'sent_at' => 'datetime',
        'ack_at' => 'datetime',
        'failed_at' => 'datetime',
    ];
}


