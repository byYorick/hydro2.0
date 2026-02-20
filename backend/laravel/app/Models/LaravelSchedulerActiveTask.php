<?php

namespace App\Models;

use Illuminate\Database\Eloquent\Factories\HasFactory;
use Illuminate\Database\Eloquent\Model;

class LaravelSchedulerActiveTask extends Model
{
    use HasFactory;

    protected $table = 'laravel_scheduler_active_tasks';

    protected $fillable = [
        'task_id',
        'zone_id',
        'task_type',
        'schedule_key',
        'correlation_id',
        'status',
        'accepted_at',
        'due_at',
        'expires_at',
        'last_polled_at',
        'terminal_at',
        'details',
    ];

    protected $casts = [
        'accepted_at' => 'immutable_datetime',
        'due_at' => 'immutable_datetime',
        'expires_at' => 'immutable_datetime',
        'last_polled_at' => 'immutable_datetime',
        'terminal_at' => 'immutable_datetime',
        'details' => 'array',
    ];
}

