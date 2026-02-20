<?php

namespace App\Models;

use Illuminate\Database\Eloquent\Factories\HasFactory;
use Illuminate\Database\Eloquent\Model;

class LaravelSchedulerZoneCursor extends Model
{
    use HasFactory;

    protected $table = 'laravel_scheduler_zone_cursors';

    protected $primaryKey = 'zone_id';

    public $incrementing = false;

    protected $keyType = 'int';

    protected $fillable = [
        'zone_id',
        'cursor_at',
        'catchup_policy',
        'metadata',
    ];

    protected $casts = [
        'cursor_at' => 'immutable_datetime',
        'metadata' => 'array',
    ];
}

