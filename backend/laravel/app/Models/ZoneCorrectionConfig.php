<?php

namespace App\Models;

use Illuminate\Database\Eloquent\Factories\HasFactory;
use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\Relations\BelongsTo;
use Illuminate\Database\Eloquent\Relations\HasMany;

class ZoneCorrectionConfig extends Model
{
    use HasFactory;

    protected $fillable = [
        'zone_id',
        'preset_id',
        'base_config',
        'phase_overrides',
        'resolved_config',
        'version',
        'updated_by',
        'last_applied_at',
        'last_applied_version',
    ];

    protected $casts = [
        'base_config' => 'array',
        'phase_overrides' => 'array',
        'resolved_config' => 'array',
        'last_applied_at' => 'datetime',
        'last_applied_version' => 'integer',
    ];

    public function zone(): BelongsTo
    {
        return $this->belongsTo(Zone::class);
    }

    public function preset(): BelongsTo
    {
        return $this->belongsTo(ZoneCorrectionPreset::class, 'preset_id');
    }

    public function updatedBy(): BelongsTo
    {
        return $this->belongsTo(User::class, 'updated_by');
    }

    public function versions(): HasMany
    {
        return $this->hasMany(ZoneCorrectionConfigVersion::class);
    }
}
