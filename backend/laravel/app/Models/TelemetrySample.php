<?php

namespace App\Models;

use Illuminate\Database\Eloquent\Factories\HasFactory;
use Illuminate\Database\Eloquent\Model;

class TelemetrySample extends Model
{
    use HasFactory;

    public $timestamps = false;

    protected $fillable = [
        'zone_id',
        'node_id',
        'channel',
        'metric_type',
        'value',
        'raw',
        'ts',
    ];

    protected $casts = [
        'raw' => 'array',
        'ts' => 'datetime',
    ];
}


