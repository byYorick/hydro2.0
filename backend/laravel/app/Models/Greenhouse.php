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
    ];

    protected $hidden = [
        // Legacy column — never expose (not a bind mechanism).
        'provisioning_token',
    ];

    protected $casts = [
        'coordinates' => 'array',
    ];

    public function zones(): HasMany
    {
        return $this->hasMany(Zone::class);
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
