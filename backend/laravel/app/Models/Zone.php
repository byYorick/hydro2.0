<?php

namespace App\Models;

use App\Enums\GrowCycleStatus;
use Illuminate\Database\Eloquent\Factories\HasFactory;
use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\Relations\BelongsTo;
use Illuminate\Database\Eloquent\Relations\HasMany;
use Illuminate\Database\Eloquent\Relations\HasOne;

class Zone extends Model
{
    use HasFactory;

    protected $fillable = [
        'uid',
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

    /**
     * Активный цикл выращивания (RUNNING или PAUSED)
     */
    public function activeGrowCycle(): HasOne
    {
        return $this->hasOne(GrowCycle::class)
            ->whereIn('status', [GrowCycleStatus::PLANNED, GrowCycleStatus::RUNNING, GrowCycleStatus::PAUSED]);
    }

    /**
     * Экземпляры инфраструктуры зоны
     */
    public function infrastructureInstances(): HasMany
    {
        return $this->morphMany(InfrastructureInstance::class, 'owner')
            ->where('owner_type', 'zone');
    }

    /**
     * Привязки каналов через инфраструктуру зоны
     */
    public function channelBindings(): HasMany
    {
        return $this->hasManyThrough(
            ChannelBinding::class,
            InfrastructureInstance::class,
            'owner_id', // Foreign key on infrastructure_instances
            'infrastructure_instance_id', // Foreign key on channel_bindings
            'id', // Local key on zones
            'id' // Local key on infrastructure_instances
        )->where('infrastructure_instances.owner_type', 'zone');
    }

    /**
     * @deprecated Используйте activeGrowCycle() вместо recipeInstance()
     */
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

    public function pidConfigs(): HasMany
    {
        return $this->hasMany(ZonePidConfig::class);
    }

    public function growCycles(): HasMany
    {
        return $this->hasMany(GrowCycle::class);
    }

    /**
     * @deprecated Используйте infrastructureInstances() вместо infrastructure()
     */
    public function infrastructure(): HasMany
    {
        return $this->hasMany(ZoneInfrastructure::class);
    }

    /**
     * @deprecated Используйте channelBindings() (новая модель) вместо старой
     */
    public function legacyChannelBindings(): HasMany
    {
        return $this->hasMany(ZoneChannelBinding::class);
    }

    /**
     * Проверка валидности инфраструктуры зоны (новая модель)
     * Все required-оборудование должно быть привязано к каналам
     */
    public function isInfrastructureValid(): bool
    {
        $requiredAssets = $this->infrastructureInstances()
            ->where('required', true)
            ->get();

        foreach ($requiredAssets as $asset) {
            if ($asset->channelBindings()->count() === 0) {
                return false;
            }
        }

        return true;
    }

    /**
     * Получить список незаполненных required-оборудований (новая модель)
     */
    public function getMissingRequiredAssets(): array
    {
        $requiredAssets = $this->infrastructureInstances()
            ->where('required', true)
            ->get();

        $missing = [];
        foreach ($requiredAssets as $asset) {
            if ($asset->channelBindings()->count() === 0) {
                $missing[] = [
                    'id' => $asset->id,
                    'type' => $asset->asset_type,
                    'label' => $asset->label,
                ];
            }
        }

        return $missing;
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
