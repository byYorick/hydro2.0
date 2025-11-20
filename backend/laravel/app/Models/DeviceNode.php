<?php

namespace App\Models;

use App\Enums\NodeLifecycleState;
use App\Events\NodeConfigUpdated;
use Illuminate\Database\Eloquent\Factories\HasFactory;
use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\Relations\BelongsTo;
use Illuminate\Database\Eloquent\Relations\HasMany;

class DeviceNode extends Model
{
    use HasFactory;

    protected $table = 'nodes';

    protected $fillable = [
        'zone_id',
        'uid',
        'name',
        'type',
        'fw_version',
        'hardware_revision',
        'hardware_id',
        'last_seen_at',
        'last_heartbeat_at',
        'first_seen_at',
        'status',
        'lifecycle_state',
        'validated',
        'uptime_seconds',
        'free_heap_bytes',
        'rssi',
        'config',
    ];

    protected $casts = [
        'last_seen_at' => 'datetime',
        'last_heartbeat_at' => 'datetime',
        'first_seen_at' => 'datetime',
        'validated' => 'boolean',
        'config' => 'array',
        'lifecycle_state' => NodeLifecycleState::class,
    ];

    protected $attributes = [
        'lifecycle_state' => NodeLifecycleState::UNPROVISIONED->value,
        'status' => 'offline',
    ];

    /**
     * Boot the model.
     */
    protected static function boot(): void
    {
        parent::boot();

        // Отправляем событие при обновлении узла (если изменились поля, влияющие на конфиг)
        static::saved(function (DeviceNode $node) {
            // Проверяем, изменились ли поля, влияющие на конфиг
            if ($node->wasChanged(['zone_id', 'type', 'config', 'uid']) || 
                $node->wasRecentlyCreated) {
                event(new NodeConfigUpdated($node));
            }
            
            // Очищаем кеш списка устройств при создании или обновлении ноды
            // Это гарантирует, что фронтенд увидит новые ноды сразу
            try {
                \Illuminate\Support\Facades\Cache::tags(['devices_list'])->flush();
            } catch (\BadMethodCallException $e) {
                // Если теги не поддерживаются, очищаем весь кеш
                // В production лучше использовать Redis с тегами
                \Illuminate\Support\Facades\Cache::flush();
            }
        });
    }

    public function zone(): BelongsTo
    {
        return $this->belongsTo(Zone::class);
    }

    public function channels(): HasMany
    {
        return $this->hasMany(NodeChannel::class, 'node_id');
    }

    public function nodeLogs(): HasMany
    {
        return $this->hasMany(NodeLog::class, 'node_id');
    }

    /**
     * Получить состояние жизненного цикла как Enum.
     */
    public function lifecycleState(): NodeLifecycleState
    {
        return $this->lifecycle_state ?? NodeLifecycleState::UNPROVISIONED;
    }

    /**
     * Проверить, может ли узел принимать телеметрию.
     */
    public function canReceiveTelemetry(): bool
    {
        return $this->lifecycleState()->canReceiveTelemetry();
    }

    /**
     * Проверить, является ли узел активным.
     */
    public function isActive(): bool
    {
        return $this->lifecycleState()->isActive();
    }

    /**
     * Проверить, является ли узел неактивным.
     */
    public function isInactive(): bool
    {
        return $this->lifecycleState()->isInactive();
    }

    /**
     * Переход в состояние PROVISIONED_WIFI.
     */
    public function transitionToProvisioned(): void
    {
        $this->lifecycle_state = NodeLifecycleState::PROVISIONED_WIFI;
        $this->save();
    }

    /**
     * Переход в состояние REGISTERED_BACKEND.
     */
    public function transitionToRegistered(): void
    {
        $this->lifecycle_state = NodeLifecycleState::REGISTERED_BACKEND;
        $this->save();
    }

    /**
     * Переход в состояние ASSIGNED_TO_ZONE.
     */
    public function transitionToAssigned(): void
    {
        $this->lifecycle_state = NodeLifecycleState::ASSIGNED_TO_ZONE;
        $this->save();
    }

    /**
     * Переход в состояние ACTIVE.
     */
    public function transitionToActive(): void
    {
        $this->lifecycle_state = NodeLifecycleState::ACTIVE;
        $this->status = 'online';
        $this->save();
    }

    /**
     * Переход в состояние DEGRADED.
     */
    public function transitionToDegraded(): void
    {
        $this->lifecycle_state = NodeLifecycleState::DEGRADED;
        $this->save();
    }

    /**
     * Переход в состояние MAINTENANCE.
     */
    public function transitionToMaintenance(): void
    {
        $this->lifecycle_state = NodeLifecycleState::MAINTENANCE;
        $this->save();
    }

    /**
     * Переход в состояние DECOMMISSIONED.
     */
    public function transitionToDecommissioned(): void
    {
        $this->lifecycle_state = NodeLifecycleState::DECOMMISSIONED;
        $this->save();
    }
}
