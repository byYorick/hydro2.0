<?php

namespace App\Listeners;

use App\Events\NodeConfigUpdated;
use App\Jobs\PublishNodeConfigJob;
use Illuminate\Support\Facades\Log;

class PublishNodeConfigOnUpdate
{
    /**
     * Create the event listener.
     */
    public function __construct()
    {
        //
    }

    /**
     * Handle the event.
     * 
     * КРИТИЧНО: Публикует конфиг ТОЛЬКО при привязке узла к зоне (pending_zone_id установлен, zone_id = null).
     * 
     * Событие NodeConfigUpdated также используется для обновления фронтенда через WebSocket,
     * но публикация конфига в MQTT происходит только при привязке узла к зоне.
     * 
     * Выполняется после коммита транзакции, чтобы не блокировать БД.
     * Использует Job с дедупликацией для предотвращения множественных публикаций.
     */
    public function handle(NodeConfigUpdated $event): void
    {
        $node = $event->node->fresh(); // Загружаем свежие данные из БД
        
        // КРИТИЧНО: Публикуем конфиг ТОЛЬКО при привязке узла к зоне
        // Условие: pending_zone_id установлен, zone_id еще null (привязка в процессе)
        // НЕ публикуем:
        // - При изменении каналов (NodeChannel вызывает событие для WebSocket)
        // - При отвязке узла (detach вызывает событие для WebSocket)
        // - При обновлении других полей
        $shouldPublishConfig = $node->pending_zone_id && !$node->zone_id;
        
        if (!$shouldPublishConfig) {
            Log::debug('PublishNodeConfigOnUpdate: Skipping config publish (not a zone attachment)', [
                'node_id' => $node->id,
                'uid' => $node->uid,
                'pending_zone_id' => $node->pending_zone_id,
                'zone_id' => $node->zone_id,
                'lifecycle_state' => $node->lifecycle_state?->value,
                'reason' => 'Config publish only happens when node is attached to zone (pending_zone_id set, zone_id null)',
            ]);
            return;
        }
        
        // Диспатчим Job с дедупликацией для предотвращения множественных публикаций
        // Дедупликация работает через Cache lock в Job
        // Используем очередь по умолчанию: в dev окружении крутится только worker для default,
        // отдельный worker для config-publish не поднимается и задания зависали.
        PublishNodeConfigJob::dispatch($node->id);
        
        Log::info('PublishNodeConfigOnUpdate: Dispatched config publish job (node attached to zone)', [
            'node_id' => $node->id,
            'uid' => $node->uid,
            'pending_zone_id' => $node->pending_zone_id,
            'zone_id' => $node->zone_id,
            'lifecycle_state' => $node->lifecycle_state?->value,
        ]);
    }
}
