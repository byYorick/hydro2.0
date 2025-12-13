<?php

namespace App\Models;

use Illuminate\Database\Eloquent\Factories\HasFactory;
use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\Relations\BelongsTo;

class ZoneEvent extends Model
{
    use HasFactory;

    public $timestamps = false;

    protected $fillable = [
        'zone_id',
        'type',
        'payload_json',  // Используем payload_json вместо details (колонка переименована в миграции)
        'entity_type',
        'entity_id',
        'server_ts',
    ];

    protected $casts = [
        'payload_json' => 'array',  // Используем payload_json вместо details
        'created_at' => 'datetime',
    ];
    
    // Accessor для обратной совместимости с кодом, использующим 'details'
    public function getDetailsAttribute()
    {
        return $this->payload_json;
    }
    
    // Mutator для обратной совместимости
    public function setDetailsAttribute($value)
    {
        $this->payload_json = $value;
    }

    public function zone(): BelongsTo
    {
        return $this->belongsTo(Zone::class);
    }
}

