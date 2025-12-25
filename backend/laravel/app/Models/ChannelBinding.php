<?php

namespace App\Models;

use Illuminate\Database\Eloquent\Factories\HasFactory;
use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\Relations\BelongsTo;

class ChannelBinding extends Model
{
    use HasFactory;

    protected $fillable = [
        'infrastructure_instance_id',
        'node_id',
        'channel',
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
     * Нода, к которой привязан канал
     */
    public function node(): BelongsTo
    {
        return $this->belongsTo(DeviceNode::class, 'node_id');
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
}

