<?php

namespace App\Models;

use Illuminate\Database\Eloquent\Factories\HasFactory;
use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\Relations\BelongsTo;
use Illuminate\Database\Eloquent\Relations\HasMany;

class DeviceNode extends Model
{
    use HasFactory;

    protected $table = 'nodes';

    protected $fillable = [
        'zone_id',
        'uid',
        'name',
        'type',
        'fw_version',
        'last_seen_at',
        'status',
        'config',
    ];

    protected $casts = [
        'last_seen_at' => 'datetime',
        'config' => 'array',
    ];

    public function zone(): BelongsTo
    {
        return $this->belongsTo(Zone::class);
    }

    public function channels(): HasMany
    {
        return $this->hasMany(NodeChannel::class, 'node_id');
    }
}


