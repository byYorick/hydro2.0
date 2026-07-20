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
        'pending_zone_set_at',
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
        'pending_zone_set_at' => 'datetime',
        'validated' => 'boolean',
        'config' => 'array',
        'lifecycle_state' => NodeLifecycleState::class,
    ];

    /**
     * Атрибуты, которые должны быть скрыты при сериализации.
     */
    protected $hidden = [
        'config', // Никогда не сериализуется в JSON (защита Wi-Fi паролей и MQTT кредов)
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

        // TTL-якорь для pending bind: ставим при установке pending_zone_id, чистим при сбросе.
        static::saving(function (DeviceNode $node) {
            if (! $node->isDirty('pending_zone_id')) {
                return;
            }

            if ($node->pending_zone_id) {
                $node->pending_zone_set_at = now();
            } else {
                $node->pending_zone_set_at = null;
            }
        });

        // Публикуем событие для новых нод, чтобы они появлялись в UI (unassigned list)
        static::created(function (DeviceNode $node) {
            if (! app()->environment('testing')) {
                \Illuminate\Support\Facades\Log::info('DeviceNode: Dispatching NodeConfigUpdated event (node created)', [
                    'node_id' => $node->id,
                    'uid' => $node->uid,
                    'zone_id' => $node->zone_id,
                    'pending_zone_id' => $node->pending_zone_id,
                    'lifecycle_state' => $node->lifecycle_state?->value,
                ]);
            }

            \Illuminate\Support\Facades\DB::afterCommit(function () use ($node) {
                event(new NodeConfigUpdated($node));
            });
        });

        // КРИТИЧНО: Отправляем обновление на фронтенд только при привязке узла к зоне (изменение pending_zone_id)
        // Используем afterCommit, чтобы событие срабатывало только после коммита транзакции
        static::saved(function (DeviceNode $node) {
            $isNewNode = $node->wasRecentlyCreated;

            // ВАЖНО: Обновление фронтенда отправляется ТОЛЬКО при изменении pending_zone_id (привязка к зоне через UI)
            // Не отправляем событие при:
            // - Изменении других полей (config, zone_id, type, uid)
            // - Обновлении узла от history-logger (завершение привязки)
            // - Первичной регистрации узла (node_hello)
            $shouldBroadcastOnAttach = ! $isNewNode && $node->pending_zone_id && ! $node->zone_id && $node->wasChanged('pending_zone_id');

            // НЕ отправляем событие если узел уже в ASSIGNED_TO_ZONE и zone_id установлен
            $skipAlreadyAssigned = $node->lifecycleState() === NodeLifecycleState::ASSIGNED_TO_ZONE && $node->zone_id;

            if (! $isNewNode && ! $skipAlreadyAssigned && $shouldBroadcastOnAttach) {
                // Отправляем событие только при привязке узла к зоне (изменение pending_zone_id)
                if (! app()->environment('testing')) {
                    \Illuminate\Support\Facades\Log::info('DeviceNode: Dispatching NodeConfigUpdated event (node attached to zone)', [
                        'node_id' => $node->id,
                        'uid' => $node->uid,
                        'pending_zone_id' => $node->pending_zone_id,
                        'zone_id' => $node->zone_id,
                        'lifecycle_state' => $node->lifecycle_state?->value,
                        'reason' => 'pending_zone_id changed - node attached to zone',
                    ]);
                }

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
                    'devices_list_zone_'.($node->zone_id ?? 'null'),
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
     * Переход в состояние PROVISIONED_WIFI (через NodeLifecycleService FSM).
     */
    public function transitionToProvisioned(?string $reason = null): bool
    {
        return app(\App\Services\NodeLifecycleService::class)
            ->transitionToProvisioned($this, $reason);
    }

    /**
     * Переход в состояние REGISTERED_BACKEND (через NodeLifecycleService FSM).
     */
    public function transitionToRegistered(?string $reason = null): bool
    {
        return app(\App\Services\NodeLifecycleService::class)
            ->transitionToRegistered($this, $reason);
    }

    /**
     * Переход в состояние ASSIGNED_TO_ZONE (через NodeLifecycleService FSM).
     */
    public function transitionToAssigned(?string $reason = null): bool
    {
        return app(\App\Services\NodeLifecycleService::class)
            ->transitionToAssigned($this, $reason);
    }

    /**
     * Переход в состояние ACTIVE (через NodeLifecycleService FSM).
     */
    public function transitionToActive(?string $reason = null): bool
    {
        return app(\App\Services\NodeLifecycleService::class)
            ->transitionToActive($this, $reason);
    }

    /**
     * Переход в состояние DEGRADED (через NodeLifecycleService FSM).
     */
    public function transitionToDegraded(?string $reason = null): bool
    {
        return app(\App\Services\NodeLifecycleService::class)
            ->transitionToDegraded($this, $reason);
    }

    /**
     * Переход в состояние MAINTENANCE (через NodeLifecycleService FSM).
     */
    public function transitionToMaintenance(?string $reason = null): bool
    {
        return app(\App\Services\NodeLifecycleService::class)
            ->transitionToMaintenance($this, $reason);
    }

    /**
     * Переход в состояние DECOMMISSIONED (через NodeLifecycleService FSM).
     */
    public function transitionToDecommissioned(?string $reason = null): bool
    {
        return app(\App\Services\NodeLifecycleService::class)
            ->transitionToDecommissioned($this, $reason);
    }
}
