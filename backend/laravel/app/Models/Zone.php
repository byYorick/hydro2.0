<?php

namespace App\Models;

use Illuminate\Database\Eloquent\Factories\HasFactory;
use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\Relations\BelongsTo;
use Illuminate\Database\Eloquent\Relations\HasMany;
use Illuminate\Database\Eloquent\Relations\HasOne;

class Zone extends Model
{
    use HasFactory;

    protected $fillable = [
        'greenhouse_id',
        'preset_id',
        'name',
        'description',
        'status',
        'health_score',
        'health_status',
        'hardware_profile',
        'capabilities',
        'water_state',
        'solution_started_at',
        'settings',
    ];

    protected $casts = [
        'hardware_profile' => 'array',
        'capabilities' => 'array',
        'settings' => 'array',
        'solution_started_at' => 'datetime',
    ];

    public function greenhouse(): BelongsTo
    {
        return $this->belongsTo(Greenhouse::class);
    }

    public function preset(): BelongsTo
    {
        return $this->belongsTo(Preset::class);
    }

    public function nodes(): HasMany
    {
        return $this->hasMany(DeviceNode::class, 'zone_id');
    }

    public function recipeInstance(): HasOne
    {
        return $this->hasOne(ZoneRecipeInstance::class);
    }

    public function alerts(): HasMany
    {
        return $this->hasMany(Alert::class);
    }

    public function predictions(): HasMany
    {
        return $this->hasMany(ParameterPrediction::class);
    }

    public function simulations(): HasMany
    {
        return $this->hasMany(ZoneSimulation::class);
    }

    public function modelParams(): HasMany
    {
        return $this->hasMany(ZoneModelParams::class);
    }

    public function zoneEvents(): HasMany
    {
        return $this->hasMany(ZoneEvent::class);
    }

    public function aiLogs(): HasMany
    {
        return $this->hasMany(AiLog::class);
    }

    /**
     * Проверка возможности управления pH
     */
    public function canPhControl(): bool
    {
        $capabilities = $this->capabilities ?? [];
        return $capabilities['ph_control'] ?? false;
    }

    /**
     * Проверка возможности управления EC
     */
    public function canEcControl(): bool
    {
        $capabilities = $this->capabilities ?? [];
        return $capabilities['ec_control'] ?? false;
    }

    /**
     * Проверка возможности управления климатом
     */
    public function canClimateControl(): bool
    {
        $capabilities = $this->capabilities ?? [];
        return $capabilities['climate_control'] ?? false;
    }

    /**
     * Проверка возможности управления освещением
     */
    public function canLightControl(): bool
    {
        $capabilities = $this->capabilities ?? [];
        return $capabilities['light_control'] ?? false;
    }

    /**
     * Проверка возможности управления поливом
     */
    public function canIrrigationControl(): bool
    {
        $capabilities = $this->capabilities ?? [];
        return $capabilities['irrigation_control'] ?? false;
    }

    /**
     * Проверка возможности рециркуляции
     */
    public function canRecirculation(): bool
    {
        $capabilities = $this->capabilities ?? [];
        return $capabilities['recirculation'] ?? false;
    }

    /**
     * Проверка наличия датчика расхода
     */
    public function hasFlowSensor(): bool
    {
        $capabilities = $this->capabilities ?? [];
        return $capabilities['flow_sensor'] ?? false;
    }
}


