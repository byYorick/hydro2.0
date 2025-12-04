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
     * Выполняется после коммита транзакции, чтобы не блокировать БД.
     * Использует Job с дедупликацией для предотвращения множественных публикаций.
     */
    public function handle(NodeConfigUpdated $event): void
    {
        $node = $event->node;
        
        // Диспатчим Job с дедупликацией для предотвращения множественных публикаций
        // Дедупликация работает через Cache lock в Job
        PublishNodeConfigJob::dispatch($node->id)
            ->onQueue('config-publish'); // Отдельная очередь для публикации конфигов
        
        Log::info('PublishNodeConfigOnUpdate: Dispatched job for node', [
            'node_id' => $node->id,
            'uid' => $node->uid,
            'pending_zone_id' => $node->pending_zone_id,
            'zone_id' => $node->zone_id,
            'lifecycle_state' => $node->lifecycle_state?->value,
        ]);
        Log::info('PublishNodeConfigOnUpdate: Job dispatched to queue', [
            'queue' => 'config-publish',
            'node_id' => $node->id,
        ]);
    }
}
