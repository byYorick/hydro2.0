<?php

namespace App\Models;

use Illuminate\Database\Eloquent\Factories\HasFactory;
use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\Relations\BelongsTo;

class TelemetrySample extends Model
{
    use HasFactory;

    protected $table = 'telemetry_samples';

    protected $fillable = [
        'sensor_id',
        'ts',
        'zone_id',
        'cycle_id',
        'value',
        'quality',
        'metadata',
    ];

    protected $casts = [
        'ts' => 'datetime',
        'value' => 'decimal:4',
        'metadata' => 'array',
    ];

    public $timestamps = false; // Используем created_at вместо timestamps

    /**
     * Сенсор
     */
    public function sensor(): BelongsTo
    {
        return $this->belongsTo(Sensor::class);
    }

    /**
     * Зона (проставляется сервером)
     */
    public function zone(): BelongsTo
    {
        return $this->belongsTo(Zone::class);
    }

    /**
     * Цикл выращивания (проставляется сервером)
     */
    public function cycle(): BelongsTo
    {
        return $this->belongsTo(GrowCycle::class, 'cycle_id');
    }

    /**
     * Scope для качественных данных
     */
    public function scopeGood($query)
    {
        return $query->where('quality', 'GOOD');
    }

    /**
     * Scope для данных зоны
     */
    public function scopeForZone($query, int $zoneId)
    {
        return $query->where('zone_id', $zoneId);
    }

    /**
     * Scope для данных цикла
     */
    public function scopeForCycle($query, int $cycleId)
    {
        return $query->where('cycle_id', $cycleId);
    }

    /**
     * Scope для временного диапазона
     */
    public function scopeInTimeRange($query, $start, $end)
    {
        return $query->whereBetween('ts', [$start, $end]);
    }
}
