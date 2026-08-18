<?php

namespace App\Models;

use Illuminate\Database\Eloquent\Factories\HasFactory;
use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\Relations\BelongsTo;
use Illuminate\Database\Eloquent\Relations\HasMany;
use Illuminate\Database\Eloquent\Relations\HasOne;

class Greenhouse extends Model
{
    use HasFactory;

    protected $fillable = [
        'uid',
        // Legacy: DB NOT NULL unique; not used for node binding (pending drop migration).
        'provisioning_token',
        'name',
        'timezone',
        'type',
        'greenhouse_type_id',
        'coordinates',
        'description',
        'is_system',
        'shared_weather_station_node_id',
    ];

    protected $hidden = [
        // Legacy column — never expose (not a bind mechanism).
        'provisioning_token',
    ];

    protected $casts = [
        'coordinates' => 'array',
        'is_system' => 'boolean',
    ];

    /**
     * @param  \Illuminate\Database\Eloquent\Builder<Greenhouse>  $query
     * @return \Illuminate\Database\Eloquent\Builder<Greenhouse>
     */
    public function scopeUserVisible($query)
    {
        return $query->where('is_system', false);
    }

    public function zones(): HasMany
    {
        return $this->hasMany(Zone::class);
    }

    public function sharedWeatherStation(): BelongsTo
    {
        return $this->belongsTo(DeviceNode::class, 'shared_weather_station_node_id');
    }

    public function greenhouseType(): BelongsTo
    {
        return $this->belongsTo(GreenhouseType::class);
    }

    public function growCycles(): HasMany
    {
        return $this->hasMany(GrowCycle::class);
    }

    /**
     * Экземпляры инфраструктуры теплицы (климат: вентиляция, проветривание, подогрев)
     */
    public function infrastructureInstances(): HasMany
    {
        return $this->morphMany(InfrastructureInstance::class, 'owner')
            ->where('owner_type', 'greenhouse');
    }

    public function automationState(): HasOne
    {
        return $this->hasOne(GreenhouseAutomationState::class);
    }
}
