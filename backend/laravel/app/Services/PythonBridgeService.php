<?php

namespace App\Services;

use App\Models\Command;
use App\Models\DeviceNode;
use App\Models\Zone;
use Illuminate\Http\Client\ConnectionException;
use Illuminate\Http\Client\RequestException;
use Illuminate\Http\Client\TimeoutException;
use Illuminate\Support\Facades\Config;
use Illuminate\Support\Facades\Http;
use Illuminate\Support\Facades\Log;
use Illuminate\Support\Str;

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

        // Получаем node_uid и channel из payload или определяем автоматически
        $nodeUid = $payload['node_uid'] ?? null;
        $channel = $payload['channel'] ?? null;

        // Если node_uid и channel не указаны, пытаемся определить их автоматически
        if (! $nodeUid || ! $channel) {
            $resolved = $this->resolveNodeAndChannel($zone, $payload['type'] ?? 'unknown', $payload['params'] ?? []);
            if ($resolved) {
                $nodeUid = $resolved['node_uid'];
                $channel = $resolved['channel'];
                Log::info('PythonBridgeService: Auto-resolved node and channel for zone command', [
                    'zone_id' => $zone->id,
                    'command_type' => $payload['type'] ?? 'unknown',
                    'node_uid' => $nodeUid,
                    'channel' => $channel,
                ]);
            } else {
                $this->markCommandFailed($command, 'Unable to auto-resolve node_uid and channel. Please specify them explicitly.');
                throw new \InvalidArgumentException(
                    'Unable to auto-resolve node_uid and channel for command type "'.($payload['type'] ?? 'unknown').'". '.
                    'Please specify target device and channel explicitly.'
                );
            }
        }

        // Валидируем, что нода существует и привязана к зоне
        $node = DeviceNode::where('uid', $nodeUid)->where('zone_id', $zone->id)->first();
        if (! $node) {
            $this->markCommandFailed($command, "Node {$nodeUid} not found or not assigned to zone {$zone->id}");
            throw new \InvalidArgumentException(
                "Node {$nodeUid} not found or not assigned to zone {$zone->id}"
            );
        }

        // Валидируем, что канал существует у ноды
        $channelExists = $node->channels()->where('channel', $channel)->exists();
        if (! $channelExists) {
            $this->markCommandFailed($command, "Channel {$channel} not found on node {$nodeUid}");
            throw new \InvalidArgumentException(
                "Channel {$channel} not found on node {$nodeUid}"
            );
        }

        // Используем history-logger для всех команд (все общение бэка с нодами через history-logger)
        $baseUrl = Config::get('services.history_logger.url');
        if (! $baseUrl) {
            $error = 'History Logger URL not configured';
            Log::error('PythonBridgeService: '.$error, [
'zone_id' => $zone->id,
                'cmd_id' => $cmdId,
            ]);
            $this->markCommandFailed($command, $error);
            throw new \RuntimeException($error);
        }

        $token = Config::get('services.history_logger.token') ?? Config::get('services.python_bridge.token'); // Fallback на старый токен
        $headers = $token ? ['Authorization' => "Bearer {$token}"] : [];

        // Ensure params is an associative array (dict), not a list
        // Python service expects Dict[str, Any], not a list
        // Empty array [] serializes to [] in JSON, but we need {} for Python
        $params = $command->params ?? [];
        if (is_array($params) && array_is_list($params)) {
            // Convert indexed array to empty object (will serialize as {} in JSON)
            $params = new \stdClass;
        } elseif (empty($params) && is_array($params)) {
            // Empty associative array - convert to object to ensure {} in JSON
            $params = new \stdClass;
        }

        // Получаем zone_uid для команды
        $zoneUid = $zone->uid ?? null;
        
        $requestData = [
            'type' => $command->cmd,
            'params' => $params,
            'greenhouse_uid' => $ghUid,
            'zone_uid' => $zoneUid, // Передаем zone_uid
            'node_uid' => $nodeUid,
            'hardware_id' => $node->hardware_id, // Передаем hardware_id для временного топика
            'channel' => $channel,
            'cmd_id' => $cmdId, // Pass Laravel's cmd_id to Python service
        ];

        try {
            $this->sendWithRetry(
                "{$baseUrl}/zones/{$zone->id}/commands",
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

        // Используем history-logger для всех команд (все общение бэка с нодами через history-logger)
        $baseUrl = Config::get('services.history_logger.url');
        if (! $baseUrl) {
            $error = 'History Logger URL not configured';
            Log::error('PythonBridgeService: '.$error, [
                'node_id' => $node->id,
                'node_uid' => $node->uid,
                'cmd_id' => $cmdId,
            ]);
            $this->markCommandFailed($command, $error);
            throw new \RuntimeException($error);
        }

        $token = Config::get('services.history_logger.token') ?? Config::get('services.python_bridge.token'); // Fallback на старый токен
        $headers = $token ? ['Authorization' => "Bearer {$token}"] : [];

        // Ensure params is an associative array (dict), not a list
        // Python service expects Dict[str, Any], not a list
        // Empty array [] serializes to [] in JSON, but we need {} for Python
        $params = $command->params ?? [];
        if (is_array($params) && array_is_list($params)) {
            // Convert indexed array to empty object (will serialize as {} in JSON)
            $params = new \stdClass;
        } elseif (empty($params) && is_array($params)) {
            // Empty associative array - convert to object to ensure {} in JSON
            $params = new \stdClass;
        }

        // Получаем zone_uid для команды
        $zoneUid = null;
        if ($zoneId && $node->zone) {
            $zoneUid = $node->zone->uid;
        }
        
        $requestData = [
            'type' => $command->cmd,
            'params' => $params,
            'greenhouse_uid' => $ghUid,
            'zone_id' => $zoneId,
            'zone_uid' => $zoneUid, // Передаем zone_uid
            'node_uid' => $node->uid,
            'hardware_id' => $node->hardware_id, // Передаем hardware_id для временного топика
            'channel' => $payload['channel'] ?? null,
            'cmd_id' => $cmdId, // Pass Laravel's cmd_id to Python service
        ];

        try {
            $this->sendWithRetry(
                "{$baseUrl}/nodes/{$node->uid}/commands",
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

        if (! $baseUrl) {
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
     * Автоматически определяет node_uid и channel для команды зоны на основе типа команды
     */
    private function resolveNodeAndChannel(Zone $zone, string $commandType, array $params = []): ?array
    {
        // Маппинг типов команд к типам нод и каналам
        $commandMapping = [
            'FORCE_PH_CONTROL' => [
                'node_type' => 'ph',
                'channels' => ['pump_acid', 'pump_base'], // Пробуем оба, выбираем первый доступный
            ],
            'FORCE_EC_CONTROL' => [
                'node_type' => 'ec',
                'channels' => ['pump_nutrient'],
            ],
            'FORCE_IRRIGATION' => [
                'node_type' => 'irrig',
                'channels' => ['pump_irrigation', 'valve_irrigation'],
            ],
            'FORCE_LIGHTING' => [
                'node_type' => 'light',
                'channels' => ['white_light', 'uv_light'],
            ],
            'FORCE_CLIMATE' => [
                'node_type' => 'climate',
                'channels' => ['fan_air', 'heater_air'],
            ],
        ];

        if (! isset($commandMapping[$commandType])) {
            Log::warning('PythonBridgeService: Unknown command type for auto-resolution', [
                'command_type' => $commandType,
                'zone_id' => $zone->id,
            ]);

            return null;
        }

        $mapping = $commandMapping[$commandType];
        $nodeType = $mapping['node_type'];
        $channels = $mapping['channels'];

        // Ищем первую доступную ноду нужного типа в зоне
        $node = DeviceNode::where('zone_id', $zone->id)
            ->where('type', $nodeType)
            ->where('status', 'online')
            ->first();

        if (! $node) {
            Log::warning('PythonBridgeService: No online node found for command type', [
                'command_type' => $commandType,
                'node_type' => $nodeType,
                'zone_id' => $zone->id,
            ]);

            return null;
        }

        // Ищем первый доступный канал из списка
        foreach ($channels as $channelName) {
            $channelExists = $node->channels()->where('channel', $channelName)->exists();
            if ($channelExists) {
                return [
                    'node_uid' => $node->uid,
                    'channel' => $channelName,
                ];
            }
        }

        // Если ни один канал не найден, пробуем любой канал типа ACTUATOR для этой ноды
        $anyActuatorChannel = $node->channels()
            ->where('type', 'ACTUATOR')
            ->first();

        if ($anyActuatorChannel) {
            Log::info('PythonBridgeService: Using fallback actuator channel', [
                'command_type' => $commandType,
                'node_uid' => $node->uid,
                'channel' => $anyActuatorChannel->channel,
                'zone_id' => $zone->id,
            ]);

            return [
                'node_uid' => $node->uid,
                'channel' => $anyActuatorChannel->channel,
            ];
        }

        Log::warning('PythonBridgeService: No suitable channel found for command type', [
            'command_type' => $commandType,
            'node_uid' => $node->uid,
            'node_type' => $nodeType,
            'zone_id' => $zone->id,
            'expected_channels' => $channels,
        ]);

        return null;
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
