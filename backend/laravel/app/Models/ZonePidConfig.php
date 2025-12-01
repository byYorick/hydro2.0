<?php

namespace App\Models;

use Database\Factories\ZonePidConfigFactory;
use Illuminate\Database\Eloquent\Factories\HasFactory;
use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\Relations\BelongsTo;

class ZonePidConfig extends Model
{
    use HasFactory;

    /**
     * Create a new factory instance for the model.
     */
    protected static function newFactory()
    {
        return ZonePidConfigFactory::new();
    }

    public $timestamps = false; // Используем только updated_at

    protected $fillable = [
        'zone_id',
        'type',
        'config',
        'updated_by',
    ];

    protected $casts = [
        'config' => 'array',
        'updated_at' => 'datetime',
    ];

    /**
     * Связь с зоной
     */
    public function zone(): BelongsTo
    {
        return $this->belongsTo(Zone::class);
    }

    /**
     * Связь с пользователем, который обновил конфиг
     */
    public function updatedBy(): BelongsTo
    {
        return $this->belongsTo(User::class, 'updated_by');
    }

    /**
     * Accessor для удобного доступа к target
     */
    public function getTargetAttribute(): ?float
    {
        return $this->config['target'] ?? null;
    }

    /**
     * Accessor для удобного доступа к dead_zone
     */
    public function getDeadZoneAttribute(): ?float
    {
        return $this->config['dead_zone'] ?? null;
    }

    /**
     * Accessor для удобного доступа к close_zone
     */
    public function getCloseZoneAttribute(): ?float
    {
        return $this->config['close_zone'] ?? null;
    }

    /**
     * Accessor для удобного доступа к far_zone
     */
    public function getFarZoneAttribute(): ?float
    {
        return $this->config['far_zone'] ?? null;
    }

    /**
     * Accessor для удобного доступа к коэффициентам зоны close
     */
    public function getCloseCoeffsAttribute(): ?array
    {
        return $this->config['zone_coeffs']['close'] ?? null;
    }

    /**
     * Accessor для удобного доступа к коэффициентам зоны far
     */
    public function getFarCoeffsAttribute(): ?array
    {
        return $this->config['zone_coeffs']['far'] ?? null;
    }

    /**
     * Accessor для удобного доступа к max_output
     */
    public function getMaxOutputAttribute(): ?float
    {
        return $this->config['max_output'] ?? null;
    }

    /**
     * Accessor для удобного доступа к min_interval_ms
     */
    public function getMinIntervalMsAttribute(): ?int
    {
        return $this->config['min_interval_ms'] ?? null;
    }

    /**
     * Accessor для удобного доступа к enable_autotune
     */
    public function getEnableAutotuneAttribute(): ?bool
    {
        return $this->config['enable_autotune'] ?? null;
    }

    /**
     * Accessor для удобного доступа к adaptation_rate
     */
    public function getAdaptationRateAttribute(): ?float
    {
        return $this->config['adaptation_rate'] ?? null;
    }
}
