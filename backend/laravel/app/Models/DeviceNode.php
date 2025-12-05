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
        'pending_zone_id',
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
        // Используем afterCommit, чтобы событие срабатывало только после коммита транзакции
        // Это предотвращает публикацию конфига до коммита или при откате транзакции
        static::saved(function (DeviceNode $node) {
            // Проверяем, изменились ли поля, влияющие на конфиг
            // pending_zone_id также влияет на конфиг, так как конфиг должен быть отправлен при установке pending_zone_id
            $changedFields = ['zone_id', 'pending_zone_id', 'type', 'config', 'uid'];
            $hasChanges = $node->wasChanged($changedFields);
            
            // ВАЖНО: НЕ публикуем конфиг для новых узлов без zone_id или pending_zone_id
            // Если нода отправила node_hello, значит у неё уже есть рабочие настройки WiFi/MQTT
            // Публикация произойдет только после привязки к зоне (установки pending_zone_id)
            $skipNewNodeWithoutZone = $node->wasRecentlyCreated && !$node->zone_id && !$node->pending_zone_id;
            
            // ВАЖНО: Если pending_zone_id установлен, но zone_id еще null, нужно отправить конфиг
            // ТОЛЬКО если pending_zone_id ИЗМЕНИЛСЯ (первая привязка к зоне)
            // Не публикуем повторно при каждом обновлении узла
            $needsConfigPublish = $node->pending_zone_id && !$node->zone_id && $node->wasChanged('pending_zone_id');
            
            // НЕ публикуем конфиг если узел уже в ASSIGNED_TO_ZONE и zone_id установлен
            // (завершение привязки уже произошло)
            $skipAlreadyAssigned = $node->lifecycleState() === NodeLifecycleState::ASSIGNED_TO_ZONE && $node->zone_id;
            
            if ($skipNewNodeWithoutZone) {
                \Illuminate\Support\Facades\Log::info('DeviceNode: Skipping config publish for new node without zone assignment', [
                    'node_id' => $node->id,
                    'uid' => $node->uid,
                    'reason' => 'Node sent node_hello, already has working WiFi/MQTT config',
                    'lifecycle_state' => $node->lifecycle_state?->value,
                ]);
            } elseif ($skipAlreadyAssigned) {
                \Illuminate\Support\Facades\Log::info('DeviceNode: Skipping config publish for already assigned node', [
                    'node_id' => $node->id,
                    'uid' => $node->uid,
                    'zone_id' => $node->zone_id,
                    'lifecycle_state' => $node->lifecycle_state?->value,
                    'reason' => 'Node already assigned and configured',
                ]);
            } elseif ($hasChanges || $needsConfigPublish) {
               \Illuminate\Support\Facades\Log::info('DeviceNode: Dispatching NodeConfigUpdated event', [
                   'node_id' => $node->id,
                   'uid' => $node->uid,
                   'changed_fields' => array_filter($changedFields, fn($field) => $node->wasChanged($field)),
                   'was_recently_created' => $node->wasRecentlyCreated,
                   'needs_config_publish' => $needsConfigPublish,
                   'pending_zone_id' => $node->pending_zone_id,
                   'zone_id' => $node->zone_id,
                   'lifecycle_state' => $node->lifecycle_state?->value,
               ]);
               \Illuminate\Support\Facades\Log::info('DeviceNode: Event will be dispatched after commit', [
                   'node_id' => $node->id,
                   'uid' => $node->uid,
               ]);
                
                // Используем afterCommit, чтобы событие срабатывало только после коммита транзакции
                \Illuminate\Support\Facades\DB::afterCommit(function () use ($node) {
                    event(new NodeConfigUpdated($node));
                });
            }
            
            // Очищаем кеш списка устройств при создании или обновлении ноды
            // Используем точечную очистку вместо глобального flush для предотвращения DoS
            try {
                \Illuminate\Support\Facades\Cache::tags(['devices_list'])->flush();
            } catch (\BadMethodCallException $e) {
                // Если теги не поддерживаются, очищаем только конкретные ключи
                // Используем паттерн для поиска ключей кеша устройств
                $cacheKeys = [
                    'devices_list_all',
                    'devices_list_zone_' . ($node->zone_id ?? 'null'),
                    'devices_list_unassigned',
                ];
                foreach ($cacheKeys as $key) {
                    \Illuminate\Support\Facades\Cache::forget($key);
                }
                // НЕ используем Cache::flush() - это может привести к DoS при массовых обновлениях
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
