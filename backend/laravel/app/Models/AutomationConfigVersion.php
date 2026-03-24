<?php

namespace App\Models;

use Illuminate\Database\Eloquent\Factories\HasFactory;
use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\Relations\BelongsTo;

class AutomationConfigVersion extends Model
{
    use HasFactory;

    protected $fillable = [
        'document_id',
        'namespace',
        'scope_type',
        'scope_id',
        'schema_version',
        'payload',
        'status',
        'source',
        'checksum',
        'changed_by',
        'changed_at',
    ];

    protected $casts = [
        'payload' => 'array',
        'changed_at' => 'datetime',
    ];

    public function document(): BelongsTo
    {
        return $this->belongsTo(AutomationConfigDocument::class, 'document_id');
    }

    public function changedBy(): BelongsTo
    {
        return $this->belongsTo(User::class, 'changed_by');
    }
}
