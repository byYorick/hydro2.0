<?php

namespace App\Services;

use App\Models\Command;
use App\Models\DeviceNode;
use App\Models\Zone;
use Illuminate\Support\Facades\Config;
use Illuminate\Support\Facades\Http;
use Illuminate\Support\Facades\Log;
use Illuminate\Support\Str;
use Illuminate\Http\Client\RequestException;
use Illuminate\Http\Client\ConnectionException;
use Illuminate\Http\Client\TimeoutException;

class PythonBridgeService
{
    public function sendZoneCommand(Zone $zone, array $payload): string
    {
        $cmdId = Str::uuid()->toString();
        $command = Command::create([
            'zone_id' => $zone->id,
            'cmd' => $payload['type'] ?? ($payload['cmd'] ?? 'unknown'),
            'params' => $payload['params'] ?? [],
            'status' => 'pending',
            'cmd_id' => $cmdId,
        ]);
        $ghUid = optional($zone->greenhouse)->uid ?? 'gh-1';
        
        // Получаем node_uid и channel из payload - они обязательны
        $nodeUid = $payload['node_uid'] ?? null;
        $channel = $payload['channel'] ?? null;
        
        // Проверяем, что node_uid и channel указаны явно
        if (!$nodeUid || !$channel) {
            $this->markCommandFailed($command, 'node_uid and channel are required');
            throw new \InvalidArgumentException(
                'node_uid and channel are required. ' .
                'Please specify target device and channel explicitly to prevent accidental commands.'
            );
        }
        
        // Валидируем, что нода существует и привязана к зоне
        $node = DeviceNode::where('uid', $nodeUid)->where('zone_id', $zone->id)->first();
        if (!$node) {
            $this->markCommandFailed($command, "Node {$nodeUid} not found or not assigned to zone {$zone->id}");
            throw new \InvalidArgumentException(
                "Node {$nodeUid} not found or not assigned to zone {$zone->id}"
            );
        }
        
        // Валидируем, что канал существует у ноды
        $channelExists = $node->channels()->where('channel', $channel)->exists();
        if (!$channelExists) {
            $this->markCommandFailed($command, "Channel {$channel} not found on node {$nodeUid}");
            throw new \InvalidArgumentException(
                "Channel {$channel} not found on node {$nodeUid}"
            );
        }
        
        $baseUrl = Config::get('services.python_bridge.base_url');
        if (!$baseUrl) {
            $error = 'Python bridge base_url not configured';
            Log::error('PythonBridgeService: ' . $error, [
                'zone_id' => $zone->id,
                'cmd_id' => $cmdId,
            ]);
            $this->markCommandFailed($command, $error);
            throw new \RuntimeException($error);
        }
        
        $token = Config::get('services.python_bridge.token');
        $headers = $token ? ['Authorization' => "Bearer {$token}"] : [];
        
        // Ensure params is an associative array (dict), not a list
        // Python service expects Dict[str, Any], not a list
        // Empty array [] serializes to [] in JSON, but we need {} for Python
        $params = $command->params ?? [];
        if (is_array($params) && array_is_list($params)) {
            // Convert indexed array to empty object (will serialize as {} in JSON)
            $params = new \stdClass();
        } elseif (empty($params) && is_array($params)) {
            // Empty associative array - convert to object to ensure {} in JSON
            $params = new \stdClass();
        }
        
        $requestData = [
            'type' => $command->cmd,
            'params' => $params,
            'greenhouse_uid' => $ghUid,
            'node_uid' => $nodeUid,
            'channel' => $channel,
            'cmd_id' => $cmdId, // Pass Laravel's cmd_id to Python service
        ];
        
        try {
            $this->sendWithRetry(
                "{$baseUrl}/bridge/zones/{$zone->id}/commands",
                $headers,
                $requestData,
                $command
            );
        } catch (\Exception $e) {
            $error = $e->getMessage();
            Log::error('PythonBridgeService: Failed to send zone command after retries', [
                'zone_id' => $zone->id,
                'cmd_id' => $cmdId,
                'error' => $error,
                'exception' => get_class($e),
            ]);
            $this->markCommandFailed($command, $error);
            throw $e;
        }
        
        return $cmdId;
    }

    public function sendNodeCommand(DeviceNode $node, array $payload): string
    {
        $cmdId = Str::uuid()->toString();
        $command = Command::create([
            'zone_id' => $node->zone_id,
            'node_id' => $node->id,
            'channel' => $payload['channel'] ?? null,
            'cmd' => $payload['type'] ?? ($payload['cmd'] ?? 'unknown'),
            'params' => $payload['params'] ?? [],
            'status' => 'pending',
            'cmd_id' => $cmdId,
        ]);
        $zoneId = $node->zone_id ?? ($payload['zone_id'] ?? null);
        $ghUid = optional(optional($node->zone)->greenhouse)->uid ?? 'gh-1';
        
        $baseUrl = Config::get('services.python_bridge.base_url');
        if (!$baseUrl) {
            $error = 'Python bridge base_url not configured';
            Log::error('PythonBridgeService: ' . $error, [
                'node_id' => $node->id,
                'node_uid' => $node->uid,
                'cmd_id' => $cmdId,
            ]);
            $this->markCommandFailed($command, $error);
            throw new \RuntimeException($error);
        }
        
        $token = Config::get('services.python_bridge.token');
        $headers = $token ? ['Authorization' => "Bearer {$token}"] : [];
        
        // Ensure params is an associative array (dict), not a list
        // Python service expects Dict[str, Any], not a list
        // Empty array [] serializes to [] in JSON, but we need {} for Python
        $params = $command->params ?? [];
        if (is_array($params) && array_is_list($params)) {
            // Convert indexed array to empty object (will serialize as {} in JSON)
            $params = new \stdClass();
        } elseif (empty($params) && is_array($params)) {
            // Empty associative array - convert to object to ensure {} in JSON
            $params = new \stdClass();
        }
        
        $requestData = [
            'type' => $command->cmd,
            'params' => $params,
            'greenhouse_uid' => $ghUid,
            'zone_id' => $zoneId,
            'channel' => $payload['channel'] ?? null,
            'cmd_id' => $cmdId, // Pass Laravel's cmd_id to Python service
        ];
        
        try {
            $this->sendWithRetry(
                "{$baseUrl}/bridge/nodes/{$node->uid}/commands",
                $headers,
                $requestData,
                $command
            );
        } catch (\Exception $e) {
            $error = $e->getMessage();
            Log::error('PythonBridgeService: Failed to send node command after retries', [
                'node_id' => $node->id,
                'node_uid' => $node->uid,
                'cmd_id' => $cmdId,
                'error' => $error,
                'exception' => get_class($e),
            ]);
            $this->markCommandFailed($command, $error);
            throw $e;
        }
        
        return $cmdId;
    }

    /**
     * Уведомить Python-сервис об обновлении конфигурации зоны
     */
    public function notifyConfigUpdate(Zone $zone): void
    {
        $baseUrl = Config::get('services.python_bridge.base_url');
        $token = Config::get('services.python_bridge.token');
        
        if (!$baseUrl) {
            // Если URL не настроен, просто логируем
            \Illuminate\Support\Facades\Log::info('Python bridge URL not configured, skipping config update notification');
            return;
        }

        try {
            $headers = $token ? ['Authorization' => "Bearer {$token}"] : [];
            
            // Отправляем уведомление о необходимости перезагрузить конфигурацию
            // Python-сервис должен сделать запрос к /api/system/config/full
            Http::withHeaders($headers)
                ->timeout(5)
                ->post("{$baseUrl}/bridge/config/zone-updated", [
                    'zone_id' => $zone->id,
                    'greenhouse_uid' => optional($zone->greenhouse)->uid,
                ]);
                
            \Illuminate\Support\Facades\Log::info('Python service notified about zone config update', [
                'zone_id' => $zone->id,
            ]);
        } catch (\Exception $e) {
            // Не бросаем исключение, чтобы не прерывать основной процесс
            \Illuminate\Support\Facades\Log::warning('Failed to notify Python service about zone config update', [
                'zone_id' => $zone->id,
                'error' => $e->getMessage(),
            ]);
        }
    }

    /**
     * Отправляет HTTP запрос с повторными попытками при ошибках
     */
    private function sendWithRetry(string $url, array $headers, array $data, Command $command): void
    {
        $timeout = Config::get('services.python_bridge.timeout', 10);
        $maxAttempts = Config::get('services.python_bridge.retry_attempts', 2);
        $retryDelay = Config::get('services.python_bridge.retry_delay', 1);
        
        $lastException = null;
        
        for ($attempt = 1; $attempt <= $maxAttempts; $attempt++) {
            try {
                $response = Http::withHeaders($headers)
                    ->timeout($timeout)
                    ->post($url, $data);
                
                // Проверяем успешность ответа
                if ($response->successful()) {
                    Log::debug('PythonBridgeService: Command sent successfully', [
                        'cmd_id' => $command->cmd_id,
                        'url' => $url,
                        'attempt' => $attempt,
                    ]);
                    return;
                }
                
                // Если ответ неуспешный, но не критическая ошибка сети
                $status = $response->status();
                $body = $response->body();
                $lastException = new RequestException(
                    "HTTP {$status}: {$body}",
                    $response->toPsrResponse()
                );
                
                Log::warning('PythonBridgeService: Non-successful response', [
                    'cmd_id' => $command->cmd_id,
                    'url' => $url,
                    'status' => $status,
                    'body' => substr($body, 0, 500), // Ограничиваем длину лога
                    'attempt' => $attempt,
                ]);
                
            } catch (ConnectionException $e) {
                $lastException = $e;
                Log::warning('PythonBridgeService: Connection error', [
                    'cmd_id' => $command->cmd_id,
                    'url' => $url,
                    'error' => $e->getMessage(),
                    'attempt' => $attempt,
                ]);
            } catch (TimeoutException $e) {
                $lastException = $e;
                Log::warning('PythonBridgeService: Timeout error', [
                    'cmd_id' => $command->cmd_id,
                    'url' => $url,
                    'timeout' => $timeout,
                    'attempt' => $attempt,
                ]);
            } catch (RequestException $e) {
                $lastException = $e;
                Log::warning('PythonBridgeService: Request error', [
                    'cmd_id' => $command->cmd_id,
                    'url' => $url,
                    'error' => $e->getMessage(),
                    'attempt' => $attempt,
                ]);
            } catch (\Exception $e) {
                $lastException = $e;
                Log::error('PythonBridgeService: Unexpected error', [
                    'cmd_id' => $command->cmd_id,
                    'url' => $url,
                    'error' => $e->getMessage(),
                    'exception' => get_class($e),
                    'attempt' => $attempt,
                ]);
            }
            
            // Если это не последняя попытка, ждем перед повтором
            if ($attempt < $maxAttempts) {
                sleep($retryDelay);
            }
        }
        
        // Все попытки исчерпаны
        throw $lastException ?? new \RuntimeException('Failed to send command: unknown error');
    }

    /**
     * Помечает команду как failed в базе данных
     */
    private function markCommandFailed(Command $command, string $error): void
    {
        try {
            $command->update([
                'status' => 'failed',
                'failed_at' => now(),
            ]);
            
            Log::info('PythonBridgeService: Command marked as failed', [
                'cmd_id' => $command->cmd_id,
                'error' => $error,
            ]);
        } catch (\Exception $e) {
            // Логируем ошибку, но не прерываем выполнение
            Log::error('PythonBridgeService: Failed to mark command as failed', [
                'cmd_id' => $command->cmd_id,
                'error' => $e->getMessage(),
            ]);
        }
    }
}


