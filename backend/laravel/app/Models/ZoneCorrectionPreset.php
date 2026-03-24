<?php

namespace App\Models;

use Illuminate\Database\Eloquent\Factories\HasFactory;
use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\Relations\BelongsTo;

class ZoneCorrectionPreset extends Model
{
    use HasFactory;

    protected $fillable = [
        'slug',
        'name',
        'scope',
        'is_locked',
        'is_active',
        'description',
        'config',
        'created_by',
        'updated_by',
    ];

    protected $casts = [
        'is_locked' => 'boolean',
        'is_active' => 'boolean',
        'config' => 'array',
    ];

    public function createdBy(): BelongsTo
    {
        return $this->belongsTo(User::class, 'created_by');
    }

    public function updatedBy(): BelongsTo
    {
        return $this->belongsTo(User::class, 'updated_by');
    }

}
