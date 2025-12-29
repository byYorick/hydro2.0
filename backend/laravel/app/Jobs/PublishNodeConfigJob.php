<?php

namespace App\Jobs;

use App\Models\DeviceNode;
use App\Services\NodeConfigService;
use App\Helpers\TransactionHelper;
use App\Enums\NodeLifecycleState;
use Illuminate\Bus\Queueable;
use Illuminate\Contracts\Queue\ShouldQueue;
use Illuminate\Foundation\Bus\Dispatchable;
use Illuminate\Http\Client\ConnectionException;
use Illuminate\Http\Client\RequestException;
use Illuminate\Http\Client\TimeoutException;
use Illuminate\Queue\InteractsWithQueue;
use Illuminate\Queue\SerializesModels;
use Illuminate\Support\Facades\Cache;
use Illuminate\Support\Facades\Config;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Http;
use Illuminate\Support\Facades\Log;

class PublishNodeConfigJob implements ShouldQueue
{
    use Dispatchable, InteractsWithQueue, Queueable, SerializesModels;

    public int $timeout = 30; // 30 секунд на публикацию конфига

    public int $tries = 2; // Максимум 2 попытки

    /**
     * Create a new job instance.
     */
    public function __construct(
        public int $nodeId,
        public ?string $dedupeKey = null
    ) {
        // Генерируем ключ дедупликации, если не передан
        if (! $dedupeKey) {
            $this->dedupeKey = "publish_config:node:{$nodeId}";
        }
    }

    /**
     * Execute the job.
     */
    public function handle(NodeConfigService $configService): void
    {
        Log::info('PublishNodeConfigJob: Config publishing disabled, skipping', [
            'node_id' => $this->nodeId,
            'dedupe_key' => $this->dedupeKey,
        ]);
        return;

        // Быстрая проверка через Redis (для производительности)
        $lockKey = "lock:{$this->dedupeKey}";
        $lock = Cache::lock($lockKey, 60); // Блокировка на 60 секунд

        if (! $lock->get()) {
            Log::debug('PublishNodeConfigJob: Skipping duplicate job (Redis lock)', [
                'node_id' => $this->nodeId,
                'dedupe_key' => $this->dedupeKey,
            ]);

            return; // Уже выполняется, пропускаем
        }

        try {
            // Используем TransactionHelper для SERIALIZABLE isolation, retry логики и advisory lock
            // Advisory lock должен быть внутри транзакции с SERIALIZABLE, поэтому сначала serializable retry
            $result = TransactionHelper::withSerializableRetry(function () use ($configService) {
                $lockResult = TransactionHelper::withAdvisoryLock(
                    "publish_config:{$this->nodeId}",
                    function () use ($configService) {
                        // Используем SELECT FOR UPDATE для защиты от конкурентных изменений
                        $node = DeviceNode::where('id', $this->nodeId)
                            ->lockForUpdate()
                            ->first();
                        
                        if (! $node) {
                            Log::warning('PublishNodeConfigJob: Node not found', [
                                'node_id' => $this->nodeId,
                            ]);

                            return;
                        }

                        // Проверяем, что узел в состоянии, когда можно публиковать конфиг
                        if (! $node->lifecycleState()->canReceiveTelemetry()) {
                            Log::debug('PublishNodeConfigJob: Skipping config publish for node', [
                                'node_id' => $node->id,
                                'uid' => $node->uid,
                                'lifecycle_state' => $node->lifecycle_state?->value,
                            ]);

                            return;
                        }

                        // Проверяем, что узел привязан к зоне или есть pending_zone_id
                        $targetZoneId = $node->zone_id ?? $node->pending_zone_id;
                        if (! $targetZoneId) {
                            Log::debug('PublishNodeConfigJob: Skipping config publish for unassigned node', [
                                'node_id' => $node->id,
                                'uid' => $node->uid,
                            ]);

                            return;
                        }

                        // BUGFIX: Сохраняем исходные значения ДО любых изменений
                        $originalZoneId = $node->zone_id;
                        $originalPendingZoneId = $node->pending_zone_id;
                        $zoneForConfig = null;
                        
                        // КРИТИЧНО: Определяем, нужно ли публиковать на временный топик
                        // Публикуем на временный топик ТОЛЬКО при привязке узла (pending_zone_id установлен, zone_id еще null)
                        // После успешной привязки временный топик больше не нужен
                        // BUGFIX: Проверяем ДО изменения zone_id
                        $isNodeBinding = $originalPendingZoneId && !$originalZoneId;
                        
                        if ($node->pending_zone_id && !$node->zone_id) {
                            // Загружаем зону из pending_zone_id
                            $zoneForConfig = \App\Models\Zone::with('greenhouse')->find($node->pending_zone_id);
                            if ($zoneForConfig) {
                                // Временно устанавливаем zone_id для генерации конфига
                                $node->zone_id = $node->pending_zone_id;
                                $node->setRelation('zone', $zoneForConfig);
                            }
                        } else {
                            // Загружаем зону для генерации конфига
                            $node->load('zone.greenhouse');
                        }

                        // Генерируем конфиг с включением credentials для публикации через MQTT
                        // Передаём флаг привязки, чтобы релейные ноды получили временный конфиг (ACTUATOR) на этапе binding
                        $config = $configService->generateNodeConfig($node, null, true, $isNodeBinding);

                        // Получаем greenhouse_uid
                        $greenhouseUid = $node->zone?->greenhouse?->uid ?? $zoneForConfig?->greenhouse?->uid;

                        if (! $greenhouseUid) {
                            Log::warning('PublishNodeConfigJob: Cannot publish config: zone has no greenhouse', [
                                'node_id' => $node->id,
                                'zone_id' => $node->zone_id,
                            ]);

                            // BUGFIX: Восстанавливаем zone_id перед возвратом
                            if ($originalZoneId !== $node->zone_id) {
                                $node->zone_id = $originalZoneId;
                                $node->unsetRelation('zone');
                            }

                            return;
                        }

                        // Вызываем history-logger API для публикации (все общение бэка с нодами через history-logger)
                        $baseUrl = Config::get('services.history_logger.url');
                        $token = Config::get('services.history_logger.token') ?? Config::get('services.python_bridge.token'); // Fallback на старый токен

                        Log::info('PublishNodeConfigJob: Preparing to call history-logger API', [
                            'node_id' => $node->id,
                            'uid' => $node->uid,
                            'base_url' => $baseUrl,
                            'has_token' => !empty($token),
                            'target_zone_id' => $targetZoneId,
                            'greenhouse_uid' => $greenhouseUid,
                        ]);

                        if (! $baseUrl) {
                            Log::error('PublishNodeConfigJob: Cannot publish config: History Logger URL not configured', [
                                'node_id' => $node->id,
                                'uid' => $node->uid,
                            ]);

                            // BUGFIX: Восстанавливаем zone_id перед возвратом
                            if ($originalZoneId !== $node->zone_id) {
                                $node->zone_id = $originalZoneId;
                                $node->unsetRelation('zone');
                            }

                            return;
                        }

                        $headers = [];
                        if ($token) {
                            $headers['Authorization'] = "Bearer {$token}";
                        }

                        // Используем короткий таймаут
                        $timeout = 10; // секунд
                        
                        // BUGFIX: Проверяем наличие hardware_id при привязке
                        // Если hardware_id отсутствует, конфиг не будет опубликован на временный топик
                        if ($isNodeBinding && !$node->hardware_id) {
                            Log::warning('PublishNodeConfigJob: Cannot publish to temp topic: hardware_id is missing', [
                                'node_id' => $node->id,
                                'uid' => $node->uid,
                            ]);
                        }
                        
                        $requestData = [
                            'node_uid' => $node->uid,
                            'hardware_id' => ($isNodeBinding && $node->hardware_id) ? $node->hardware_id : null, // Передаем hardware_id ТОЛЬКО при привязке и если он есть
                            'zone_id' => $targetZoneId,
                            'greenhouse_uid' => $greenhouseUid,
                            'config' => $config,
                        ];
                        
                        Log::info('PublishNodeConfigJob: Request data prepared', [
                            'node_id' => $node->id,
                            'is_node_binding' => $isNodeBinding,
                            'pending_zone_id' => $node->pending_zone_id,
                            'zone_id' => $node->zone_id,
                            'has_hardware_id' => !empty($requestData['hardware_id']),
                        ]);

                        Log::info('PublishNodeConfigJob: Sending request to history-logger', [
                            'node_id' => $node->id,
                            'uid' => $node->uid,
                            'url' => "{$baseUrl}/nodes/{$node->uid}/config",
                            'request_data_keys' => array_keys($requestData),
                            'config_keys' => array_keys($config),
                        ]);

                        $response = Http::withHeaders($headers)
                            ->timeout($timeout)
                            ->post("{$baseUrl}/nodes/{$node->uid}/config", $requestData);
                        
                        // Восстанавливаем оригинальный zone_id и relation если они были изменены
                        if ($originalZoneId !== $node->zone_id) {
                            $node->zone_id = $originalZoneId;
                            $node->unsetRelation('zone');
                        }

                        if ($response->successful()) {
                            Log::info('PublishNodeConfigJob: NodeConfig published via MQTT', [
                                'node_id' => $node->id,
                                'uid' => $node->uid,
                                'topic' => $response->json('data.topic'),
                            ]);
                        } else {
                            Log::warning('PublishNodeConfigJob: Non-successful response', [
                                'node_id' => $node->id,
                                'uid' => $node->uid,
                                'status' => $response->status(),
                                'body' => substr($response->body(), 0, 500),
                            ]);
                            // RequestException принимает Response как первый аргумент
                            throw new RequestException($response);
                        }
                    });
                
                // Если блокировка не получена, возвращаем null
                return $lockResult;
            });
            
            // Если результат null, значит блокировка не была получена (дубликат операции)
            if ($result === null) {
                Log::debug('PublishNodeConfigJob: Skipping duplicate job (advisory lock not acquired)', [
                    'node_id' => $this->nodeId,
                ]);
                return;
            }
        } catch (ConnectionException|TimeoutException|RequestException $e) {
            Log::warning('PublishNodeConfigJob: Network error', [
                'node_id' => $this->nodeId,
                'error' => $e->getMessage(),
            ]);
            throw $e; // Пробрасываем для повторной попытки
        } catch (\Exception $e) {
            Log::error('PublishNodeConfigJob: Error publishing NodeConfig', [
                'node_id' => $this->nodeId,
                'error' => $e->getMessage(),
                'trace' => $e->getTraceAsString(),
            ]);
            throw $e; // Пробрасываем для повторной попытки
        } finally {
            $lock->release();
        }
    }

    /**
     * Handle a job failure.
     * БАГ #4 FIX: Откатываем pending_zone_id при ошибке публикации конфига
     */
    public function failed(\Throwable $exception): void
    {
        Log::error('PublishNodeConfigJob: Job failed permanently', [
            'node_id' => $this->nodeId,
            'error' => $exception->getMessage(),
        ]);
        
        // Откатываем pending_zone_id при ошибке публикации
        try {
            DB::transaction(function () {
                $node = DeviceNode::where('id', $this->nodeId)
                    ->lockForUpdate()
                    ->first();
                    
                if ($node && $node->pending_zone_id && !$node->zone_id) {
                    // Если конфиг не был опубликован, откатываем привязку
                    $node->pending_zone_id = null;
                    $node->lifecycle_state = NodeLifecycleState::REGISTERED_BACKEND;
                    $node->save();
                    
                    Log::warning('PublishNodeConfigJob: Rolled back pending_zone_id due to job failure', [
                        'node_id' => $node->id,
                        'uid' => $node->uid,
                    ]);
                }
            });
        } catch (\Exception $e) {
            Log::error('PublishNodeConfigJob: Error rolling back pending_zone_id', [
                'node_id' => $this->nodeId,
                'error' => $e->getMessage(),
            ]);
        }
    }
}
