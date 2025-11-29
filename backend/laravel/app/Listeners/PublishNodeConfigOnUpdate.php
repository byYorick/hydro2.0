<?php

namespace App\Listeners;

use App\Events\NodeConfigUpdated;
use App\Services\NodeConfigService;
use App\Enums\NodeLifecycleState;
use Illuminate\Support\Facades\Http;
use Illuminate\Support\Facades\Log;
use Illuminate\Support\Facades\Config;
use Illuminate\Http\Client\ConnectionException;
use Illuminate\Http\Client\TimeoutException;
use Illuminate\Http\Client\RequestException;
use Illuminate\Contracts\Events\ShouldHandleAfterCommit;

class PublishNodeConfigOnUpdate implements ShouldHandleAfterCommit
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
     * 
     * Выполняется после коммита транзакции, чтобы не блокировать БД.
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
        
        // Проверяем, был ли zone_id только что установлен (для отката при ошибке)
        $wasZoneIdJustAssigned = $node->wasChanged('zone_id') && $node->zone_id;
        
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
                // НЕ откатываем привязку - это критическая ошибка конфигурации, которую нужно исправить
                // Нода остается привязанной, но конфиг не будет опубликован до исправления проблемы
                if ($wasZoneIdJustAssigned) {
                    Log::warning('Zone has no greenhouse, but keeping zone assignment. Fix zone configuration and retry config publish', [
                        'node_id' => $node->id,
                        'uid' => $node->uid,
                        'zone_id' => $node->zone_id,
                    ]);
                }
                return;
            }
            
            // Вызываем mqtt-bridge API для публикации
            $baseUrl = Config::get('services.python_bridge.base_url');
            $token = Config::get('services.python_bridge.token');
            
            if (!$baseUrl) {
                Log::warning('Cannot publish config: MQTT bridge URL not configured');
                // НЕ откатываем привязку - это ошибка конфигурации системы
                // Нода остается привязанной, но конфиг не будет опубликован до исправления конфигурации
                if ($wasZoneIdJustAssigned) {
                    Log::warning('MQTT bridge URL not configured, but keeping zone assignment. Fix system configuration and retry config publish', [
                        'node_id' => $node->id,
                        'uid' => $node->uid,
                        'zone_id' => $node->zone_id,
                    ]);
                }
                return;
            }
            
            $headers = [];
            if ($token) {
                $headers['Authorization'] = "Bearer {$token}";
            }
            
            // Используем короткий таймаут и retry, чтобы не блокировать транзакции БД
            $timeout = 10; // секунд
            $maxAttempts = 2;
            $retryDelay = 1;
            
            $lastException = null;
            $response = null;
            
            for ($attempt = 1; $attempt <= $maxAttempts; $attempt++) {
                try {
                    $response = Http::withHeaders($headers)
                        ->timeout($timeout)
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
                            'attempt' => $attempt,
                        ]);
                        break; // Успешно, выходим из цикла
                    }
                    
                    // Неуспешный ответ, но не критическая ошибка сети
                    $lastException = new RequestException(
                        "HTTP {$response->status()}: {$response->body()}",
                        $response->toPsrResponse()
                    );
                    
                    Log::warning('NodeConfig publish: Non-successful response', [
                        'node_id' => $node->id,
                        'uid' => $node->uid,
                        'status' => $response->status(),
                        'body' => substr($response->body(), 0, 500),
                        'attempt' => $attempt,
                    ]);
                    
                } catch (ConnectionException $e) {
                    $lastException = $e;
                    Log::warning('NodeConfig publish: Connection error', [
                        'node_id' => $node->id,
                        'uid' => $node->uid,
                        'error' => $e->getMessage(),
                        'attempt' => $attempt,
                    ]);
                } catch (TimeoutException $e) {
                    $lastException = $e;
                    Log::warning('NodeConfig publish: Timeout error', [
                        'node_id' => $node->id,
                        'uid' => $node->uid,
                        'timeout' => $timeout,
                        'attempt' => $attempt,
                    ]);
                } catch (RequestException $e) {
                    $lastException = $e;
                    Log::warning('NodeConfig publish: Request error', [
                        'node_id' => $node->id,
                        'uid' => $node->uid,
                        'error' => $e->getMessage(),
                        'attempt' => $attempt,
                    ]);
                }
                
                // Если это не последняя попытка, ждем перед повтором
                if ($attempt < $maxAttempts) {
                    sleep($retryDelay);
                }
            }
            
            // Проверяем результат после всех попыток
            if ($response && $response->successful()) {
                // Успешно опубликовано
                // НЕ переводим сразу в ASSIGNED_TO_ZONE - это произойдет только после получения
                // config_response от ноды, подтверждающего успешную установку конфига
                // Обработка config_response происходит в history-logger
            } else {
                // Все попытки не удались
                Log::error('Failed to publish NodeConfig via MQTT after retries', [
                    'node_id' => $node->id,
                    'uid' => $node->uid,
                    'status' => $response?->status(),
                    'response' => $response ? substr($response->body(), 0, 500) : null,
                    'last_error' => $lastException?->getMessage(),
                ]);
                
                // НЕ откатываем привязку при ошибке публикации конфига
                // Нода остается привязанной к зоне, но в состоянии REGISTERED_BACKEND
                // Пользователь может повторить попытку публикации конфига вручную
                // Это позволяет видеть, что привязка была выполнена, но конфиг не опубликован
                if ($wasZoneIdJustAssigned) {
                    Log::warning('Config publish failed after retries, but keeping zone assignment. User can retry config publish manually', [
                        'node_id' => $node->id,
                        'uid' => $node->uid,
                        'zone_id' => $node->zone_id,
                        'last_error' => $lastException?->getMessage(),
                    ]);
                }
            }
        } catch (\Exception $e) {
            Log::error('Error publishing NodeConfig', [
                'node_id' => $node->id,
                'uid' => $node->uid,
                'error' => $e->getMessage(),
                'trace' => $e->getTraceAsString(),
            ]);
            
            // НЕ откатываем привязку при ошибке - нода остается привязанной
            // Пользователь может повторить попытку публикации конфига вручную
            if ($wasZoneIdJustAssigned) {
                Log::warning('Config publish error, but keeping zone assignment. User can retry config publish manually', [
                    'node_id' => $node->id,
                    'uid' => $node->uid,
                    'zone_id' => $node->zone_id,
                    'error' => $e->getMessage(),
                ]);
            }
        }
    }
}
