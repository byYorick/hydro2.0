<?php

namespace App\Models;

use Illuminate\Database\Eloquent\Factories\HasFactory;
use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\Relations\BelongsTo;
use Illuminate\Database\Eloquent\Relations\HasMany;

class AutomationConfigPreset extends Model
{
    use HasFactory;

    protected $fillable = [
        'namespace',
        'scope',
        'is_locked',
        'name',
        'slug',
        'description',
        'schema_version',
        'payload',
        'updated_by',
    ];

    protected $casts = [
        'is_locked' => 'boolean',
        'payload' => 'array',
    ];

    public function versions(): HasMany
    {
        return $this->hasMany(AutomationConfigPresetVersion::class, 'preset_id');
    }

    public function updatedBy(): BelongsTo
    {
        return $this->belongsTo(User::class, 'updated_by');
    }
}
