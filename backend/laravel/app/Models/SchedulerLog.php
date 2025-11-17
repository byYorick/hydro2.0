<?php

namespace App\Models;

use Illuminate\Database\Eloquent\Factories\HasFactory;
use Illuminate\Database\Eloquent\Model;

class SchedulerLog extends Model
{
    use HasFactory;

    public $timestamps = false;

    protected $fillable = [
        'task_name',
        'status',
        'details',
    ];

    protected $casts = [
        'details' => 'array',
        'created_at' => 'datetime',
    ];
}

