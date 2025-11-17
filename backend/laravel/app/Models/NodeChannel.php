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
        static::saved(function (NodeChannel $channel) {
            // Загружаем узел и отправляем событие обновления конфига
            $channel->load('node');
            if ($channel->node) {
                event(new NodeConfigUpdated($channel->node));
            }
        });

        // Отправляем событие при удалении канала
        static::deleted(function (NodeChannel $channel) {
            // Загружаем узел и отправляем событие обновления конфига
            $channel->load('node');
            if ($channel->node) {
                event(new NodeConfigUpdated($channel->node));
            }
        });
    }
}


