<?php

namespace App\Models;

use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\Relations\BelongsTo;

class ZoneAutomationPreset extends Model
{
    protected $fillable = [
        'name',
        'slug',
        'description',
        'scope',
        'is_locked',
        'tanks_count',
        'irrigation_system_type',
        'correction_preset_id',
        'correction_profile',
        'config',
        'created_by',
        'updated_by',
    ];

    protected $casts = [
        'is_locked' => 'boolean',
        'tanks_count' => 'integer',
        'config' => 'array',
    ];

    public function correctionPreset(): BelongsTo
    {
        return $this->belongsTo(AutomationConfigPreset::class, 'correction_preset_id');
    }

    public function createdBy(): BelongsTo
    {
        return $this->belongsTo(User::class, 'created_by');
    }

    public function updatedBy(): BelongsTo
    {
        return $this->belongsTo(User::class, 'updated_by');
    }
}
