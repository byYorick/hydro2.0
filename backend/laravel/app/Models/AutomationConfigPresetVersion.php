<?php

namespace App\Models;

use Illuminate\Database\Eloquent\Factories\HasFactory;
use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\Relations\BelongsTo;

class AutomationConfigPresetVersion extends Model
{
    use HasFactory;

    protected $fillable = [
        'preset_id',
        'namespace',
        'scope',
        'schema_version',
        'payload',
        'checksum',
        'changed_by',
        'changed_at',
    ];

    protected $casts = [
        'payload' => 'array',
        'changed_at' => 'datetime',
    ];

    public function preset(): BelongsTo
    {
        return $this->belongsTo(AutomationConfigPreset::class, 'preset_id');
    }

    public function changedBy(): BelongsTo
    {
        return $this->belongsTo(User::class, 'changed_by');
    }
}
