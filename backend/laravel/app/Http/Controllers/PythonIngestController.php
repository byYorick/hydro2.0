<?php

namespace App\Http\Controllers;

use App\Events\NodeTelemetryUpdated;
use App\Models\DeviceNode;
use Carbon\Carbon;
use Illuminate\Http\Request;
use Illuminate\Support\Facades\Config;
use Illuminate\Support\Facades\Http;
use Illuminate\Support\Facades\Log;
use Illuminate\Support\Facades\Response;

class PythonIngestController extends Controller
{
    private function ensureToken(Request $request): void
    {
        // Используем PY_INGEST_TOKEN как основной токен для ingest
        // Fallback на PY_API_TOKEN для обратной совместимости
        $expected = Config::get('services.python_bridge.ingest_token') ?? Config::get('services.python_bridge.token');
        $given = $request->bearerToken();

        // Если токен не настроен, всегда требуем токен (даже в testing)
        // Это обеспечивает безопасность по умолчанию
        if (! $expected) {
            throw new \Illuminate\Http\Exceptions\HttpResponseException(
                response()->json([
                    'status' => 'error',
                    'message' => 'Unauthorized: service token not configured. Set PY_INGEST_TOKEN or PY_API_TOKEN.',
                ], 401)
            );
        }

        if (! $given || ! hash_equals($expected, (string) $given)) {
            throw new \Illuminate\Http\Exceptions\HttpResponseException(
                response()->json([
                    'status' => 'error',
                    'message' => 'Unauthorized: invalid or missing service token',
                ], 401)
            );
        }
    }

    public function telemetry(Request $request)
    {
        $this->ensureToken($request);
        $data = $request->validate([
            'zone_id' => ['required', 'integer', 'exists:zones,id'],
            'node_id' => ['nullable', 'integer', 'exists:nodes,id'],
            'metric_type' => ['required', 'string', 'max:64'],
            'value' => ['required', 'numeric'],
            'ts' => ['nullable', 'date'],
            'channel' => ['nullable', 'string', 'max:64'],
        ]);

        // Проверяем, что zone_id существует
        $zone = \App\Models\Zone::find($data['zone_id']);
        if (! $zone) {
            Log::warning('PythonIngestController: Zone not found', [
                'zone_id' => $data['zone_id'],
            ]);

            return \Illuminate\Support\Facades\Response::json([
                'status' => 'error',
                'message' => 'Zone not found',
            ], 404);
        }

        // Получаем node_uid из БД и проверяем привязку node_id→zone_id
        $nodeUid = null;
        $nodeId = $data['node_id'] ?? null;
        if ($nodeId) {
            $node = DeviceNode::find($nodeId);
            if (! $node) {
                Log::warning('PythonIngestController: Node not found', [
                    'node_id' => $nodeId,
                ]);

                return \Illuminate\Support\Facades\Response::json([
                    'status' => 'error',
                    'message' => 'Node not found',
                ], 404);
            }

            // Проверяем, что нода привязана к указанной зоне
            if ($node->zone_id !== $data['zone_id']) {
                Log::warning('PythonIngestController: Node zone mismatch', [
                    'node_id' => $nodeId,
                    'node_zone_id' => $node->zone_id,
                    'requested_zone_id' => $data['zone_id'],
                ]);

                return \Illuminate\Support\Facades\Response::json([
                    'status' => 'error',
                    'message' => 'Node is not assigned to the specified zone',
                ], 422);
            }

            $nodeUid = $node->uid;
        }
        $tsValue = $data['ts'] ?? null;
        $timestamp = $tsValue ? Carbon::parse($tsValue) : now();

        // Формируем запрос для history-logger
        // Передаём zone_id напрямую (в таблице zones нет uid)
        $sample = [
            'node_uid' => $nodeUid ?? '',
            'zone_id' => $data['zone_id'],  // Передаём zone_id напрямую
            'metric_type' => $data['metric_type'],
            'value' => $data['value'],
            'ts' => $timestamp->toIso8601String(),
            'channel' => $data['channel'] ?? null,
        ];

        // Проксируем в history-logger
        try {
            $historyLoggerUrl = Config::get('services.history_logger.url', 'http://history-logger:9300');
            $response = Http::timeout(5)->post(
                $historyLoggerUrl.'/ingest/telemetry',
                ['samples' => [$sample]]
            );

            if (! $response->successful()) {
                Log::warning('History logger request failed', [
                    'status' => $response->status(),
                    'body' => $response->body(),
                ]);

                return Response::json(['status' => 'error', 'message' => 'Failed to ingest telemetry'], 500);
            }

            // Broadcast телеметрии через WebSocket для real-time обновления графиков
            if ($nodeId) {
                Log::debug('PythonIngestController: Broadcasting telemetry via WebSocket', [
                    'node_id' => $nodeId,
                    'channel' => $data['channel'] ?? '',
                    'metric_type' => $data['metric_type'],
                    'value' => $data['value'],
                ]);
                
                event(new NodeTelemetryUpdated(
                    nodeId: $nodeId,
                    channel: $data['channel'] ?? '',
                    metricType: $data['metric_type'],
                    value: (float) $data['value'],
                    timestamp: $timestamp->getTimestamp() * 1000, // Конвертируем в миллисекунды
                ));
            }

            return Response::json(['status' => 'ok']);
        } catch (\Exception $e) {
            Log::error('History logger request exception', [
                'message' => $e->getMessage(),
            ]);

            return Response::json(['status' => 'error', 'message' => 'Failed to ingest telemetry'], 500);
        }
    }

    public function commandAck(Request $request)
    {
        $this->ensureToken($request);
        $data = $request->validate([
            'cmd_id' => ['required', 'string', 'max:64'],
            'status' => ['required', 'string', 'in:ACCEPTED,DONE,FAILED,accepted,completed,failed,ack'],
            'details' => ['nullable', 'array'],
        ]);

        // Нормализуем статус: поддерживаем старые значения для обратной совместимости
        $normalizedStatus = match (strtoupper($data['status'])) {
            'ACCEPTED', 'ACK' => 'accepted',
            'DONE', 'COMPLETED' => 'completed',
            'FAILED' => 'failed',
            default => $data['status'],
        };

        // Обновляем статус команды в БД, чтобы фронт получил broadcast (CommandObserver)
        $command = \App\Models\Command::where('cmd_id', $data['cmd_id'])->latest('id')->first();
        if ($command) {
            $updates = ['status' => $normalizedStatus];

            // ACCEPTED - команда принята к выполнению
            if ($normalizedStatus === 'accepted' && ! $command->ack_at) {
                $updates['ack_at'] = now();
            }
            
            // DONE/COMPLETED - команда успешно выполнена
            if ($normalizedStatus === 'completed' && ! $command->ack_at) {
                $updates['ack_at'] = now();
            }
            
            // FAILED - команда завершилась с ошибкой
            if ($normalizedStatus === 'failed') {
                $updates['failed_at'] = now();
            }

            $command->update($updates);

            // Дополнительно сразу шлем событие с деталями ошибки/статуса, чтобы фронт получил уведомление
            $zoneId = $command->zone_id;
            $details = $data['details'] ?? [];
            $errorMessage = $details['error_message'] ?? $details['error_code'] ?? null;
            $message = $details['message'] ?? null;

            if ($normalizedStatus === 'failed') {
                event(new \App\Events\CommandFailed(
                    commandId: $command->cmd_id,
                    message: $message ?? 'Command failed',
                    error: $errorMessage,
                    zoneId: $zoneId
                ));
            } else {
                event(new \App\Events\CommandStatusUpdated(
                    commandId: $command->cmd_id,
                    status: $normalizedStatus,
                    message: $message ?? 'Command status updated',
                    error: $errorMessage,
                    zoneId: $zoneId
                ));
            }
        } else {
            Log::warning('commandAck: Command not found for cmd_id', [
                'cmd_id' => $data['cmd_id'],
                'status' => $data['status'],
                'normalized_status' => $normalizedStatus,
            ]);
        }

        return Response::json(['status' => 'ok']);
    }

    /**
     * Broadcast телеметрии через WebSocket
     * Вызывается из history-logger после сохранения телеметрии в БД
     */
    public function broadcastTelemetry(Request $request)
    {
        $this->ensureToken($request);
        $data = $request->validate([
            'node_id' => ['required', 'integer', 'exists:nodes,id'],
            'channel' => ['nullable', 'string', 'max:64'],
            'metric_type' => ['required', 'string', 'max:64'],
            'value' => ['required', 'numeric'],
            'timestamp' => ['required', 'integer'], // timestamp в миллисекундах
        ]);

        Log::debug('PythonIngestController: Broadcasting telemetry via WebSocket', [
            'node_id' => $data['node_id'],
            'channel' => $data['channel'] ?? '',
            'metric_type' => $data['metric_type'],
            'value' => $data['value'],
        ]);

        event(new NodeTelemetryUpdated(
            nodeId: $data['node_id'],
            channel: $data['channel'] ?? '',
            metricType: $data['metric_type'],
            value: (float) $data['value'],
            timestamp: $data['timestamp'],
        ));

        return Response::json(['status' => 'ok']);
    }
}
