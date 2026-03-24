<?php

namespace App\Models;

use Illuminate\Database\Eloquent\Factories\HasFactory;
use Illuminate\Database\Eloquent\Model;

class AutomationEffectiveBundle extends Model
{
    use HasFactory;

    protected $fillable = [
        'scope_type',
        'scope_id',
        'bundle_revision',
        'schema_revision',
        'config',
        'violations',
        'status',
        'compiled_at',
        'inputs_checksum',
    ];

    protected $casts = [
        'config' => 'array',
        'violations' => 'array',
        'compiled_at' => 'datetime',
    ];
}
