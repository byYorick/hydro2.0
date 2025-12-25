<?php

namespace App\Models;

use Illuminate\Database\Eloquent\Factories\HasFactory;
use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\Relations\BelongsTo;
use Illuminate\Database\Eloquent\Relations\HasMany;

class Sensor extends Model
{
    use HasFactory;

    protected $fillable = [
        'greenhouse_id',
        'zone_id',
        'node_id',
        'scope',
        'type',
        'label',
        'unit',
        'specs',
        'is_active',
        'last_read_at',
    ];

    protected $casts = [
        'specs' => 'array',
        'is_active' => 'boolean',
        'last_read_at' => 'datetime',
    ];

    /**
     * Теплица
     */
    public function greenhouse(): BelongsTo
    {
        return $this->belongsTo(Greenhouse::class);
    }

    /**
     * Зона (nullable для тепличных/наружных датчиков)
     */
    public function zone(): BelongsTo
    {
        return $this->belongsTo(Zone::class);
    }

    /**
     * Нода (если датчик физически на ноде)
     */
    public function node(): BelongsTo
    {
        return $this->belongsTo(DeviceNode::class, 'node_id');
    }

    /**
     * Образцы телеметрии
     */
    public function telemetrySamples(): HasMany
    {
        return $this->hasMany(TelemetrySample::class);
    }

    /**
     * Последнее значение (кэш)
     */
    public function lastValue(): BelongsTo
    {
        return $this->belongsTo(TelemetryLast::class, 'sensor_id', 'sensor_id');
    }

    /**
     * Scope для активных сенсоров
     */
    public function scopeActive($query)
    {
        return $query->where('is_active', true);
    }

    /**
     * Scope для зонных сенсоров
     */
    public function scopeForZone($query, int $zoneId)
    {
        return $query->where('zone_id', $zoneId);
    }

    /**
     * Scope для тепличных сенсоров
     */
    public function scopeForGreenhouse($query, int $greenhouseId, ?string $scope = null)
    {
        $query = $query->where('greenhouse_id', $greenhouseId)
            ->whereNull('zone_id');
        
        if ($scope) {
            $query->where('scope', $scope);
        }
        
        return $query;
    }
}

