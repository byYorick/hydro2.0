<?php

namespace App\Models;

use Illuminate\Database\Eloquent\Factories\HasFactory;
use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\Relations\BelongsTo;
use Illuminate\Support\Facades\DB;

class ChannelBinding extends Model
{
    use HasFactory;

    protected $fillable = [
        'infrastructure_instance_id',
        'node_channel_id',
        'direction',
        'role',
    ];

    /**
     * Экземпляр инфраструктуры, к которому привязан канал
     */
    public function infrastructureInstance(): BelongsTo
    {
        return $this->belongsTo(InfrastructureInstance::class);
    }

    /**
     * Канал ноды (нормализованная связь)
     */
    public function nodeChannel(): BelongsTo
    {
        return $this->belongsTo(NodeChannel::class);
    }

    /**
     * Нода через канал (accessor для удобства)
     */
    public function getNodeAttribute()
    {
        return $this->nodeChannel?->node;
    }

    /**
     * Scope для фильтрации по направлению
     */
    public function scopeActuators($query)
    {
        return $query->where('direction', 'actuator');
    }

    /**
     * Scope для фильтрации по направлению
     */
    public function scopeSensors($query)
    {
        return $query->where('direction', 'sensor');
    }

    /**
     * Scope для фильтрации по роли
     */
    public function scopeWithRole($query, string $role)
    {
        return $query->where('role', $role);
    }

    protected static function booted(): void
    {
        static::saved(function (ChannelBinding $binding): void {
            $role = strtolower((string) ($binding->role ?? ''));
            if ($role !== 'soil_moisture_sensor') {
                return;
            }

            DB::afterCommit(function () use ($binding): void {
                try {
                    app(\App\Services\SoilMoistureSensorBindingService::class)->provisionSensorForBinding($binding->fresh());
                } catch (\Throwable $e) {
                    \Illuminate\Support\Facades\Log::error('ChannelBinding: failed to provision soil moisture sensor', [
                        'binding_id' => $binding->id,
                        'error' => $e->getMessage(),
                    ]);
                }
            });
        });
    }
}

