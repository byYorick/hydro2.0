<?php

namespace App\Models;

use Illuminate\Database\Eloquent\Factories\HasFactory;
use Illuminate\Database\Eloquent\Model;

class AutomationConfigViolation extends Model
{
    use HasFactory;

    public $timestamps = false;

    protected $fillable = [
        'scope_type',
        'scope_id',
        'namespace',
        'path',
        'code',
        'severity',
        'blocking',
        'message',
        'detected_at',
    ];

    protected $casts = [
        'blocking' => 'boolean',
        'detected_at' => 'datetime',
    ];
}
