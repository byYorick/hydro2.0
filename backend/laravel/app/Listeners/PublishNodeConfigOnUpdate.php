<?php

namespace App\Listeners;

use App\Events\NodeConfigUpdated;
use App\Services\NodeConfigService;
use Illuminate\Support\Facades\Http;
use Illuminate\Support\Facades\Log;
use Illuminate\Support\Facades\Config;

class PublishNodeConfigOnUpdate
{
    /**
     * Create the event listener.
     */
    public function __construct(
        private NodeConfigService $configService
    ) {
        //
    }

    /**
     * Handle the event.
     */
    public function handle(NodeConfigUpdated $event): void
    {
        $node = $event->node;
        
        // Проверяем, что узел в состоянии, когда можно публиковать конфиг
        if (!$node->lifecycleState()->canReceiveTelemetry()) {
            Log::debug('Skipping config publish for node', [
                'node_id' => $node->id,
                'uid' => $node->uid,
                'lifecycle_state' => $node->lifecycle_state?->value,
            ]);
            return;
        }
        
        // Проверяем, что узел привязан к зоне
        if (!$node->zone_id) {
            Log::debug('Skipping config publish for unassigned node', [
                'node_id' => $node->id,
                'uid' => $node->uid,
            ]);
            return;
        }
        
        try {
            // Генерируем конфиг
            $config = $this->configService->generateNodeConfig($node);
            
            // Получаем greenhouse_uid
            $node->load('zone.greenhouse');
            $greenhouseUid = $node->zone?->greenhouse?->uid;
            
            if (!$greenhouseUid) {
                Log::warning('Cannot publish config: zone has no greenhouse', [
                    'node_id' => $node->id,
                    'zone_id' => $node->zone_id,
                ]);
                return;
            }
            
            // Вызываем mqtt-bridge API для публикации
            $baseUrl = Config::get('services.python_bridge.base_url');
            $token = Config::get('services.python_bridge.token');
            
            if (!$baseUrl) {
                Log::warning('Cannot publish config: MQTT bridge URL not configured');
                return;
            }
            
            $headers = [];
            if ($token) {
                $headers['Authorization'] = "Bearer {$token}";
            }
            
            $response = Http::withHeaders($headers)
                ->post("{$baseUrl}/bridge/nodes/{$node->uid}/config", [
                    'node_uid' => $node->uid,
                    'zone_id' => $node->zone_id,
                    'greenhouse_uid' => $greenhouseUid,
                    'config' => $config,
                ]);
            
            if ($response->successful()) {
                Log::info('NodeConfig published via MQTT', [
                    'node_id' => $node->id,
                    'uid' => $node->uid,
                    'topic' => $response->json('data.topic'),
                ]);
            } else {
                Log::error('Failed to publish NodeConfig via MQTT', [
                    'node_id' => $node->id,
                    'uid' => $node->uid,
                    'status' => $response->status(),
                    'response' => $response->body(),
                ]);
            }
        } catch (\Exception $e) {
            Log::error('Error publishing NodeConfig', [
                'node_id' => $node->id,
                'uid' => $node->uid,
                'error' => $e->getMessage(),
            ]);
        }
    }
}
