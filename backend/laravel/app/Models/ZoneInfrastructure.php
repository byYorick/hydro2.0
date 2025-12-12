<?php

namespace App\Models;

use Illuminate\Database\Eloquent\Factories\HasFactory;
use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\Relations\BelongsTo;
use Illuminate\Database\Eloquent\Relations\HasMany;

class ZoneInfrastructure extends Model
{
    use HasFactory;

    protected $table = 'zone_infrastructure';

    protected $fillable = [
        'zone_id',
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
     * Связь с зоной
     */
    public function zone(): BelongsTo
    {
        return $this->belongsTo(Zone::class);
    }

    /**
     * Связь с привязками каналов
     */
    public function channelBindings(): HasMany
    {
        return $this->hasMany(ZoneChannelBinding::class, 'asset_id');
    }

    /**
     * Проверка, привязано ли оборудование к каналам
     */
    public function isBound(): bool
    {
        return $this->channelBindings()->exists();
    }
}

