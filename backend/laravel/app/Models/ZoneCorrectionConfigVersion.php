<?php

namespace App\Models;

use Illuminate\Database\Eloquent\Factories\HasFactory;
use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\Relations\BelongsTo;

class ZoneCorrectionConfigVersion extends Model
{
    use HasFactory;

    protected $fillable = [
        'zone_correction_config_id',
        'zone_id',
        'preset_id',
        'version',
        'change_type',
        'base_config',
        'phase_overrides',
        'resolved_config',
        'changed_by',
        'changed_at',
    ];

    protected $casts = [
        'base_config' => 'array',
        'phase_overrides' => 'array',
        'resolved_config' => 'array',
        'changed_at' => 'datetime',
    ];

    public function zoneCorrectionConfig(): BelongsTo
    {
        return $this->belongsTo(ZoneCorrectionConfig::class);
    }

    public function zone(): BelongsTo
    {
        return $this->belongsTo(Zone::class);
    }

    public function preset(): BelongsTo
    {
        return $this->belongsTo(ZoneCorrectionPreset::class, 'preset_id');
    }

    public function changedBy(): BelongsTo
    {
        return $this->belongsTo(User::class, 'changed_by');
    }
}
