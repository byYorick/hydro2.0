<?php

namespace App\Models;

use Illuminate\Database\Eloquent\Factories\HasFactory;
use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\Relations\BelongsTo;
use Illuminate\Database\Eloquent\Relations\HasMany;
use Illuminate\Database\Eloquent\Relations\MorphTo;

class InfrastructureInstance extends Model
{
    use HasFactory;

    protected $fillable = [
        'owner_type',
        'owner_id',
        'asset_type',
        'label',
        'required',
        'capacity_liters',
        'flow_rate',
        'specs',
    ];

    protected $casts = [
        'required' => 'boolean',
        'capacity_liters' => 'decimal:2',
        'flow_rate' => 'decimal:2',
        'specs' => 'array',
    ];

    /**
     * Полиморфная связь с владельцем (зона или теплица)
     */
    public function owner(): MorphTo
    {
        return $this->morphTo();
    }

    /**
     * Привязки каналов к этому экземпляру инфраструктуры
     */
    public function channelBindings(): HasMany
    {
        return $this->hasMany(ChannelBinding::class);
    }

    /**
     * Scope для фильтрации по типу владельца
     */
    public function scopeForZone($query, int $zoneId)
    {
        return $query->where('owner_type', 'zone')
            ->where('owner_id', $zoneId);
    }

    /**
     * Scope для фильтрации по типу владельца (теплица)
     */
    public function scopeForGreenhouse($query, int $greenhouseId)
    {
        return $query->where('owner_type', 'greenhouse')
            ->where('owner_id', $greenhouseId);
    }

    /**
     * Scope для фильтрации по типу оборудования
     */
    public function scopeOfType($query, string $assetType)
    {
        return $query->where('asset_type', $assetType);
    }
}

