<?php

namespace App\Models;

use Illuminate\Database\Eloquent\Factories\HasFactory;
use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\Relations\BelongsTo;
use Illuminate\Database\Eloquent\Relations\HasMany;

class AutomationConfigDocument extends Model
{
    use HasFactory;

    protected $fillable = [
        'namespace',
        'scope_type',
        'scope_id',
        'schema_version',
        'payload',
        'status',
        'source',
        'checksum',
        'updated_by',
    ];

    protected $casts = [
        'payload' => 'array',
    ];

    public function updatedBy(): BelongsTo
    {
        return $this->belongsTo(User::class, 'updated_by');
    }

    public function versions(): HasMany
    {
        return $this->hasMany(AutomationConfigVersion::class, 'document_id');
    }
}
