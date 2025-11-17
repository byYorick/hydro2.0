<?php

namespace App\Models;

use Illuminate\Database\Eloquent\Factories\HasFactory;
use Illuminate\Database\Eloquent\Model;

class TelemetryLast extends Model
{
    use HasFactory;

    public $timestamps = false;
    protected $table = 'telemetry_last';
    protected $primaryKey = null;
    public $incrementing = false;

    protected $fillable = [
        'zone_id',
        'metric_type',
        'node_id',
        'channel',
        'value',
        'updated_at',
    ];

    protected $casts = [
        'updated_at' => 'datetime',
    ];
}


