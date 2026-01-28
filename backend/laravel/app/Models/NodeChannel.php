<?php

namespace App\Models;

use App\Events\NodeConfigUpdated;
use Illuminate\Database\Eloquent\Factories\HasFactory;
use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\Relations\BelongsTo;

class NodeChannel extends Model
{
    use HasFactory;

    protected $fillable = [
        'node_id',
        'channel',
        'type',
        'metric',
        'unit',
        'config',
    ];

    protected $casts = [
        'config' => 'array',
    ];

    /**
     * Атрибуты, которые должны быть скрыты при сериализации.
     */
    protected $hidden = [
        'config', // Никогда не сериализуется в JSON (защита параметров актуаторов)
    ];

    public function node(): BelongsTo
    {
        return $this->belongsTo(DeviceNode::class, 'node_id');
    }

    /**
     * Boot the model.
     */
    protected static function boot(): void
    {
        parent::boot();

        // Отправляем событие при сохранении канала (создании или обновлении)
        // Используем afterCommit, чтобы событие срабатывало только после коммита транзакции
        static::saved(function (NodeChannel $channel) {
            // Загружаем узел и отправляем событие обновления конфига после коммита
            $channel->load('node');
            if ($channel->node) {
                \Illuminate\Support\Facades\DB::afterCommit(function () use ($channel) {
                    event(new NodeConfigUpdated($channel->node));
                });
            }
        });

        // Отправляем событие при удалении канала
        // Используем afterCommit, чтобы событие срабатывало только после коммита транзакции
        static::deleted(function (NodeChannel $channel) {
            // Загружаем узел и отправляем событие обновления конфига после коммита
            $channel->load('node');
            if ($channel->node) {
                \Illuminate\Support\Facades\DB::afterCommit(function () use ($channel) {
                    event(new NodeConfigUpdated($channel->node));
                });
            }
        });
    }
}


