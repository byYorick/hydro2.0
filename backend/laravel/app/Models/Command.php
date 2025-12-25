<?php

namespace App\Models;

use Illuminate\Database\Eloquent\Factories\HasFactory;
use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\Relations\BelongsTo;
use Illuminate\Database\Eloquent\Relations\HasMany;

/**
 * Модель команды с единым контрактом статусов.
 * 
 * State-machine статусов:
 * - QUEUED: команда поставлена в очередь
 * - SENT: команда отправлена в MQTT
 * - ACCEPTED: команда принята узлом
 * - DONE: команда успешно выполнена
 * - FAILED: команда завершилась с ошибкой
 * - TIMEOUT: команда не получила ответа в срок
 * - SEND_FAILED: ошибка при отправке команды
 */
class Command extends Model
{
    use HasFactory;

    /**
     * Статусы команд согласно единому контракту
     */
    public const STATUS_QUEUED = 'QUEUED';
    public const STATUS_SENT = 'SENT';
    public const STATUS_ACCEPTED = 'ACCEPTED';
    public const STATUS_DONE = 'DONE';
    public const STATUS_FAILED = 'FAILED';
    public const STATUS_TIMEOUT = 'TIMEOUT';
    public const STATUS_SEND_FAILED = 'SEND_FAILED';

    /**
     * Конечные статусы (команда завершена)
     */
    public const FINAL_STATUSES = [
        self::STATUS_DONE,
        self::STATUS_FAILED,
        self::STATUS_TIMEOUT,
        self::STATUS_SEND_FAILED,
    ];

    protected $fillable = [
        'zone_id',
        'cycle_id',
        'context_type',
        'node_id',
        'channel',
        'cmd',
        'command_type',
        'params',
        'payload',
        'status',
        'cmd_id',
        'request_id',
        'sent_at',
        'ack_at',
        'failed_at',
        'error_code',
        'error_message',
        'result_code',
        'duration_ms',
    ];

    protected $casts = [
        'params' => 'array',
        'payload' => 'array',
        'sent_at' => 'datetime',
        'ack_at' => 'datetime',
        'failed_at' => 'datetime',
        'result_code' => 'integer',
        'duration_ms' => 'integer',
    ];

    /**
     * Проверяет, является ли статус конечным
     */
    public function isFinal(): bool
    {
        return in_array($this->status, self::FINAL_STATUSES, true);
    }

    /**
     * Проверяет, завершена ли команда успешно
     */
    public function isDone(): bool
    {
        return $this->status === self::STATUS_DONE;
    }

    /**
     * Проверяет, завершена ли команда с ошибкой
     */
    public function isFailed(): bool
    {
        return in_array($this->status, [
            self::STATUS_FAILED,
            self::STATUS_TIMEOUT,
            self::STATUS_SEND_FAILED,
        ], true);
    }

    /**
     * Цикл выращивания (nullable для внецикловых команд)
     */
    public function cycle(): BelongsTo
    {
        return $this->belongsTo(GrowCycle::class);
    }

    /**
     * Зона
     */
    public function zone(): BelongsTo
    {
        return $this->belongsTo(Zone::class);
    }

    /**
     * Узел
     */
    public function node(): BelongsTo
    {
        return $this->belongsTo(DeviceNode::class, 'node_id');
    }

    /**
     * Подтверждения команды (двухфазное подтверждение)
     */
    public function acks(): HasMany
    {
        return $this->hasMany(CommandAck::class);
    }

    /**
     * Последнее подтверждение
     */
    public function lastAck()
    {
        return $this->hasOne(CommandAck::class)->latestOfMany('created_at');
    }

    /**
     * Scope для команд цикла
     */
    public function scopeForCycle($query, int $cycleId)
    {
        return $query->where('cycle_id', $cycleId);
    }

    /**
     * Scope для внецикловых команд
     */
    public function scopeOutOfCycle($query)
    {
        return $query->whereNull('cycle_id');
    }

    /**
     * Scope для типа контекста
     */
    public function scopeWithContext($query, string $contextType)
    {
        return $query->where('context_type', $contextType);
    }
}


