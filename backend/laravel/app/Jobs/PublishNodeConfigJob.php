<?php

namespace App\Jobs;

use App\Models\DeviceNode;
use App\Services\NodeConfigService;
use Illuminate\Bus\Queueable;
use Illuminate\Contracts\Queue\ShouldQueue;
use Illuminate\Foundation\Bus\Dispatchable;
use Illuminate\Queue\InteractsWithQueue;
use Illuminate\Queue\SerializesModels;
use Illuminate\Support\Facades\Cache;
use Illuminate\Support\Facades\Http;
use Illuminate\Support\Facades\Log;
use Illuminate\Support\Facades\Config;
use Illuminate\Http\Client\ConnectionException;
use Illuminate\Http\Client\TimeoutException;
use Illuminate\Http\Client\RequestException;

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
        public string $dedupeKey = null
    ) {
        // Генерируем ключ дедупликации, если не передан
        if (!$dedupeKey) {
            $this->dedupeKey = "publish_config:node:{$nodeId}";
        }
    }

    /**
     * Execute the job.
     */
    public function handle(NodeConfigService $configService): void
    {
        // Дедупликация: проверяем, не выполняется ли уже публикация для этого узла
        $lockKey = "lock:{$this->dedupeKey}";
        $lock = Cache::lock($lockKey, 60); // Блокировка на 60 секунд

        if (!$lock->get()) {
            Log::debug('PublishNodeConfigJob: Skipping duplicate job', [
                'node_id' => $this->nodeId,
                'dedupe_key' => $this->dedupeKey,
            ]);
            return; // Уже выполняется, пропускаем
        }

        try {
            $node = DeviceNode::find($this->nodeId);
            if (!$node) {
                Log::warning('PublishNodeConfigJob: Node not found', [
                    'node_id' => $this->nodeId,
                ]);
                return;
            }

            // Проверяем, что узел в состоянии, когда можно публиковать конфиг
            if (!$node->lifecycleState()->canReceiveTelemetry()) {
                Log::debug('PublishNodeConfigJob: Skipping config publish for node', [
                    'node_id' => $node->id,
                    'uid' => $node->uid,
                    'lifecycle_state' => $node->lifecycle_state?->value,
                ]);
                return;
            }

            // Проверяем, что узел привязан к зоне
            if (!$node->zone_id) {
                Log::debug('PublishNodeConfigJob: Skipping config publish for unassigned node', [
                    'node_id' => $node->id,
                    'uid' => $node->uid,
                ]);
                return;
            }

            // Генерируем конфиг
            $config = $configService->generateNodeConfig($node);

            // Получаем greenhouse_uid
            $node->load('zone.greenhouse');
            $greenhouseUid = $node->zone?->greenhouse?->uid;

            if (!$greenhouseUid) {
                Log::warning('PublishNodeConfigJob: Cannot publish config: zone has no greenhouse', [
                    'node_id' => $node->id,
                    'zone_id' => $node->zone_id,
                ]);
                return;
            }

            // Вызываем mqtt-bridge API для публикации
            $baseUrl = Config::get('services.python_bridge.base_url');
            $token = Config::get('services.python_bridge.token');

            if (!$baseUrl) {
                Log::warning('PublishNodeConfigJob: Cannot publish config: MQTT bridge URL not configured');
                return;
            }

            $headers = [];
            if ($token) {
                $headers['Authorization'] = "Bearer {$token}";
            }

            // Используем короткий таймаут
            $timeout = 10; // секунд

            $response = Http::withHeaders($headers)
                ->timeout($timeout)
                ->post("{$baseUrl}/bridge/nodes/{$node->uid}/config", [
                    'node_uid' => $node->uid,
                    'zone_id' => $node->zone_id,
                    'greenhouse_uid' => $greenhouseUid,
                    'config' => $config,
                ]);

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
                throw new RequestException(
                    "HTTP {$response->status()}: {$response->body()}",
                    $response->toPsrResponse()
                );
            }
        } catch (ConnectionException | TimeoutException | RequestException $e) {
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
     */
    public function failed(\Throwable $exception): void
    {
        Log::error('PublishNodeConfigJob: Job failed permanently', [
            'node_id' => $this->nodeId,
            'error' => $exception->getMessage(),
        ]);
    }
}
