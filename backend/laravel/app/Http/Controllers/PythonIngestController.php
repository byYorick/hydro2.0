<?php

namespace App\Http\Controllers;

use App\Events\TelemetryBatchUpdated;
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

        Log::info('[COMMAND_ACK_AUTH] Token check', [
            'has_expected_token' => !empty($expected),
            'has_given_token' => !empty($given),
            'expected_token_length' => $expected ? strlen($expected) : 0,
            'given_token_length' => $given ? strlen($given) : 0,
            'tokens_match' => $expected && $given ? hash_equals($expected, (string) $given) : false,
        ]);

        // Если токен не настроен, всегда требуем токен (даже в testing)
        // Это обеспечивает безопасность по умолчанию
        if (! $expected) {
            Log::error('[COMMAND_ACK_AUTH] Token not configured in Laravel');
            throw new \Illuminate\Http\Exceptions\HttpResponseException(
                response()->json([
                    'status' => 'error',
                    'message' => 'Unauthorized: service token not configured. Set PY_INGEST_TOKEN or PY_API_TOKEN.',
                ], 401)
            );
        }

        if (! $given || ! hash_equals($expected, (string) $given)) {
            Log::warning('[COMMAND_ACK_AUTH] Token validation failed', [
                'has_given' => !empty($given),
                'token_match' => $expected && $given ? hash_equals($expected, (string) $given) : false,
            ]);
            throw new \Illuminate\Http\Exceptions\HttpResponseException(
                response()->json([
                    'status' => 'error',
                    'message' => 'Unauthorized: invalid or missing service token',
                ], 401)
            );
        }
        
        Log::info('[COMMAND_ACK_AUTH] Token validated successfully');
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
        
        // Проверка на искаженное время: если timestamp отклоняется от серверного более чем на 5 минут,
        // используем серверное время для обеспечения единой временной линии
        if ($tsValue) {
            $serverTime = now();
            $deviceTime = $timestamp;
            $driftSeconds = abs($serverTime->diffInSeconds($deviceTime, false));
            $maxDriftSeconds = 300; // 5 минут
            
            if ($driftSeconds > $maxDriftSeconds) {
                Log::warning('PythonIngestController: Device timestamp is skewed, using server time', [
                    'device_ts' => $deviceTime->toIso8601String(),
                    'server_ts' => $serverTime->toIso8601String(),
                    'drift_sec' => $driftSeconds,
                    'max_drift_sec' => $maxDriftSeconds,
                    'node_id' => $nodeId,
                    'zone_id' => $data['zone_id'],
                ]);
                $timestamp = $serverTime;
            }
        }

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
            if ($nodeId && $data['zone_id']) {
                Log::debug('PythonIngestController: Broadcasting telemetry via WebSocket', [
                    'node_id' => $nodeId,
                    'channel' => $data['channel'] ?? '',
                    'metric_type' => $data['metric_type'],
                    'value' => $data['value'],
                ]);

                event(new TelemetryBatchUpdated(
                    zoneId: (int) $data['zone_id'],
                    updates: [[
                        'node_id' => (int) $nodeId,
                        'channel' => $data['channel'] ?? null,
                        'metric_type' => (string) $data['metric_type'],
                        'value' => (float) $data['value'],
                        'ts' => (int) ($timestamp->getTimestamp() * 1000),
                    ]]
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
        Log::info('[COMMAND_ACK] STEP 0: commandAck endpoint called', [
            'method' => $request->method(),
            'url' => $request->fullUrl(),
            'ip' => $request->ip(),
            'headers' => [
                'authorization' => $request->header('Authorization') ? 'present' : 'missing',
                'content-type' => $request->header('Content-Type'),
            ],
        ]);
        
        Log::info('[COMMAND_ACK] STEP 1: Received commandAck request', [
            'cmd_id' => $request->input('cmd_id'),
            'status' => $request->input('status'),
            'has_details' => $request->has('details'),
        ]);
        
        try {
            $this->ensureToken($request);
            Log::info('[COMMAND_ACK] STEP 2: Token validated');
        } catch (\Exception $e) {
            Log::error('[COMMAND_ACK] STEP 2: Token validation failed', [
                'error' => $e->getMessage(),
                'exception' => get_class($e),
            ]);
            throw $e;
        }
        
        $data = $request->validate([
            'cmd_id' => ['required', 'string', 'max:64'],
            'status' => ['required', 'string', 'in:SENT,ACCEPTED,DONE,FAILED,TIMEOUT,SEND_FAILED,accepted,completed,failed,ack,timeout'],
            'details' => ['nullable', 'array'],
        ]);
        
        Log::info('[COMMAND_ACK] STEP 3: Request validated', ['data' => $data]);

        // Нормализуем статус в новые значения: SENT/ACCEPTED/DONE/FAILED
        // Поддерживаем старые значения для обратной совместимости
        $normalizedStatus = match (strtoupper($data['status'])) {
            'SENT' => \App\Models\Command::STATUS_SENT,
            'ACCEPTED', 'ACK' => \App\Models\Command::STATUS_ACCEPTED,
            'DONE', 'COMPLETED', 'OK', 'SUCCESS' => \App\Models\Command::STATUS_DONE,
            'FAILED', 'ERROR', 'REJECTED' => \App\Models\Command::STATUS_FAILED,
            'TIMEOUT' => \App\Models\Command::STATUS_TIMEOUT,
            'SEND_FAILED' => \App\Models\Command::STATUS_SEND_FAILED,
            default => strtoupper($data['status']), // Используем как есть, если это новый статус
        };
        
        Log::info('[COMMAND_ACK] STEP 4: Status normalized', [
            'original_status' => $data['status'],
            'normalized_status' => $normalizedStatus,
        ]);

        // Обновляем статус команды в БД, чтобы фронт получил broadcast (CommandObserver)
        Log::info('[COMMAND_ACK] STEP 5: Looking up command in database', ['cmd_id' => $data['cmd_id']]);
        $command = \App\Models\Command::where('cmd_id', $data['cmd_id'])->latest('id')->first();
        if ($command) {
            Log::info('[COMMAND_ACK] STEP 5.1: Command found', [
                'cmd_id' => $data['cmd_id'],
                'command_id' => $command->id,
                'current_status' => $command->status,
            ]);
            // State machine guard: проверяем валидность перехода статуса
            $currentStatus = $command->status;
            $newStatus = $normalizedStatus;
            
            // Определяем конечные статусы (нельзя изменять)
            $finalStatuses = [
                \App\Models\Command::STATUS_DONE,
                \App\Models\Command::STATUS_FAILED,
                \App\Models\Command::STATUS_TIMEOUT,
                \App\Models\Command::STATUS_SEND_FAILED,
            ];
            
            // Если команда уже в конечном статусе, не обновляем (запрет отката)
            if (in_array($currentStatus, $finalStatuses)) {
                Log::info('commandAck: Command already in final status, skipping update', [
                    'cmd_id' => $data['cmd_id'],
                    'current_status' => $currentStatus,
                    'attempted_status' => $newStatus,
                ]);
                
                return Response::json([
                    'status' => 'ok',
                    'message' => 'Command already in final status',
                ]);
            }
            
            // Проверяем переходы: запрещаем откат (например, DONE нельзя заменить на SENT)
            $isRollback = false;
            
            // Запрет перехода назад: если текущий статус более продвинутый, чем новый
            $statusOrder = [
                \App\Models\Command::STATUS_QUEUED => 0,
                \App\Models\Command::STATUS_SEND_FAILED => 1,
                \App\Models\Command::STATUS_SENT => 2,
                \App\Models\Command::STATUS_ACCEPTED => 3,
                \App\Models\Command::STATUS_DONE => 4,
                \App\Models\Command::STATUS_FAILED => 4,
                \App\Models\Command::STATUS_TIMEOUT => 4,
            ];
            
            $currentOrder = $statusOrder[$currentStatus] ?? 0;
            $newOrder = $statusOrder[$newStatus] ?? 0;
            
            // Запрещаем откат (кроме повторной отправки из SEND_FAILED в SENT)
            if ($newOrder < $currentOrder && !($currentStatus === \App\Models\Command::STATUS_SEND_FAILED && $newStatus === \App\Models\Command::STATUS_SENT)) {
                $isRollback = true;
            }
            
            if ($isRollback) {
                Log::warning('commandAck: Status rollback prevented by state machine guard', [
                    'cmd_id' => $data['cmd_id'],
                    'current_status' => $currentStatus,
                    'attempted_status' => $newStatus,
                ]);
                
                return Response::json([
                    'status' => 'ok',
                    'message' => 'Status rollback prevented',
                ]);
            }
            
            $updates = ['status' => $normalizedStatus];
            
            // Добавляем детали из details если есть
            $details = $data['details'] ?? [];
            if (isset($details['error_code'])) {
                $updates['error_code'] = $details['error_code'];
            }
            if (isset($details['error_message'])) {
                $updates['error_message'] = $details['error_message'];
            }
            if (isset($details['result_code'])) {
                $updates['result_code'] = $details['result_code'];
            }
            if (isset($details['duration_ms'])) {
                $updates['duration_ms'] = $details['duration_ms'];
            }

            // SENT - команда отправлена в MQTT (подтверждение корреляции)
            if ($normalizedStatus === \App\Models\Command::STATUS_SENT && ! $command->sent_at) {
                $updates['sent_at'] = now();
            }
            
            // ACCEPTED - команда принята к выполнению
            if ($normalizedStatus === \App\Models\Command::STATUS_ACCEPTED && ! $command->ack_at) {
                $updates['ack_at'] = now();
            }
            
            // DONE - команда успешно выполнена
            if ($normalizedStatus === \App\Models\Command::STATUS_DONE && ! $command->ack_at) {
                $updates['ack_at'] = now();
            }
            
            // FAILED/TIMEOUT/SEND_FAILED - команда завершилась с ошибкой
            if (in_array($normalizedStatus, [
                \App\Models\Command::STATUS_FAILED,
                \App\Models\Command::STATUS_TIMEOUT,
                \App\Models\Command::STATUS_SEND_FAILED
            ]) && ! $command->failed_at) {
                $updates['failed_at'] = now();
            }

            Log::info('[COMMAND_ACK] STEP 8: Updating command in database', [
                'cmd_id' => $data['cmd_id'],
                'updates' => $updates,
            ]);
            
            $command->update($updates);
            
            Log::info('[COMMAND_ACK] STEP 8.1: Command updated successfully', [
                'cmd_id' => $data['cmd_id'],
                'new_status' => $command->fresh()->status,
            ]);

            // Дополнительно сразу шлем событие с деталями ошибки/статуса, чтобы фронт получил уведомление
            $zoneId = $command->zone_id;
            $errorMessage = $details['error_message'] ?? $details['error_code'] ?? null;
            $message = $details['message'] ?? null;

            Log::info('[COMMAND_ACK] STEP 9: Dispatching WebSocket event', [
                'cmd_id' => $data['cmd_id'],
                'normalized_status' => $normalizedStatus,
                'zone_id' => $zoneId,
            ]);

            if (in_array($normalizedStatus, [
                \App\Models\Command::STATUS_FAILED,
                \App\Models\Command::STATUS_TIMEOUT,
                \App\Models\Command::STATUS_SEND_FAILED
            ])) {
                Log::info('[COMMAND_ACK] STEP 9.1: Dispatching CommandFailed event');
                event(new \App\Events\CommandFailed(
                    commandId: $command->cmd_id,
                    message: $message ?? 'Command failed',
                    error: $errorMessage,
                    zoneId: $zoneId
                ));
            } else {
                Log::info('[COMMAND_ACK] STEP 9.2: Dispatching CommandStatusUpdated event');
                event(new \App\Events\CommandStatusUpdated(
                    commandId: $command->cmd_id,
                    status: $normalizedStatus,
                    message: $message ?? 'Command status updated',
                    error: $errorMessage,
                    zoneId: $zoneId
                ));
            }
            
            Log::info('[COMMAND_ACK] STEP 10: Event dispatched, returning success');
        } else {
            Log::warning('[COMMAND_ACK] STEP 5.2: Command not found for cmd_id', [
                'cmd_id' => $data['cmd_id'],
                'status' => $data['status'],
                'normalized_status' => $normalizedStatus,
            ]);
        }

        Log::info('[COMMAND_ACK] STEP 11: Returning response');
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
            'zone_id' => ['nullable', 'integer', 'exists:zones,id'],
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

        $zoneId = $data['zone_id'] ?? null;
        if (! $zoneId) {
            $zoneId = DeviceNode::query()
                ->whereKey($data['node_id'])
                ->value('zone_id');
        }

        if (! $zoneId) {
            Log::debug('PythonIngestController: Skipping telemetry broadcast (zone not resolved)', [
                'node_id' => $data['node_id'],
                'metric_type' => $data['metric_type'],
            ]);

            return Response::json(['status' => 'skipped']);
        }

        event(new TelemetryBatchUpdated(
            zoneId: (int) $zoneId,
            updates: [[
                'node_id' => (int) $data['node_id'],
                'channel' => $data['channel'] ?? null,
                'metric_type' => (string) $data['metric_type'],
                'value' => (float) $data['value'],
                'ts' => (int) $data['timestamp'],
            ]]
        ));

        return Response::json(['status' => 'ok']);
    }

    public function alerts(Request $request)
    {
        $this->ensureToken($request);
        $data = $request->validate([
            'zone_id' => ['nullable', 'integer'],
            'node_uid' => ['nullable', 'string', 'max:100'],
            'hardware_id' => ['nullable', 'string', 'max:100'],
            'source' => ['required', 'string', 'in:biz,infra'],
            'code' => ['required', 'string', 'max:64'],
            'type' => ['required', 'string', 'max:64'],
            'severity' => ['nullable', 'string', 'max:32'],
            'details' => ['nullable', 'array'],
            'ts_device' => ['nullable', 'date'],
        ]);
        
        // Валидируем zone_id отдельно, если он указан (для unassigned hardware разрешаем null)
        if (isset($data['zone_id']) && $data['zone_id'] !== null) {
            $zoneExists = \App\Models\Zone::where('id', $data['zone_id'])->exists();
            if (!$zoneExists) {
                return Response::json([
                    'status' => 'error',
                    'message' => 'Zone not found',
                ], 422);
            }
        }

        try {
            $alertService = app(\App\Services\AlertService::class);
            
            // Используем createOrUpdateActive для дедупликации
            $result = $alertService->createOrUpdateActive([
                'zone_id' => $data['zone_id'] ?? null,
                'source' => $data['source'],
                'code' => $data['code'],
                'type' => $data['type'],
                'details' => $data['details'] ?? null,
                'severity' => $data['severity'] ?? null,
                'node_uid' => $data['node_uid'] ?? null,
                'hardware_id' => $data['hardware_id'] ?? null,
                'ts_device' => $data['ts_device'] ?? null,
            ]);

            $alert = $result['alert'];
            $serverTs = now()->toIso8601String();

            return Response::json([
                'status' => 'ok',
                'data' => [
                    'alert_id' => $alert->id,
                    'event_id' => $result['event_id'],
                    'server_ts' => $serverTs,
                ],
            ]);
        } catch (\Exception $e) {
            Log::error('PythonIngestController: Failed to create/update alert', [
                'error' => $e->getMessage(),
                'trace' => $e->getTraceAsString(),
                'data' => $data,
            ]);

            return Response::json([
                'status' => 'error',
                'message' => 'Failed to create/update alert: ' . $e->getMessage(),
            ], 500);
        }
    }
}
