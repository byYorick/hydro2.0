<?php

declare(strict_types=1);

namespace App\Http\Controllers\Api\Internal;

use App\Events\ExecutionChainUpdated;
use App\Http\Controllers\Controller;
use App\Models\AeTask;
use Illuminate\Http\JsonResponse;
use Illuminate\Http\Request;
use Illuminate\Support\Facades\Cache;
use Illuminate\Support\Facades\Log;
use Illuminate\Support\Facades\Validator;

/**
 * Принимает событие о прогрессе execution-а от history-logger-а и
 * ретранслирует его в broadcast-канал `hydro.zone.executions.{zoneId}`
 * для обновления cockpit-UI в реальном времени.
 *
 * Подпись проверяется в middleware `verify.history-logger.webhook`.
 * Чтобы не штормить WS при множественных ACK на одну команду, broadcast
 * дебаунсится через cache-lock (`HISTORY_LOGGER_WEBHOOK_DEBOUNCE_MS`).
 */
class HistoryLoggerWebhookController extends Controller
{
    public function executionEvent(Request $request): JsonResponse
    {
        $validator = Validator::make($request->all(), [
            'zone_id' => ['required', 'integer', 'min:1'],
            'execution_id' => ['required', 'string', 'regex:/^\d+$/'],
            'step' => ['required', 'string', 'in:SNAPSHOT,DECISION,TASK,DISPATCH,RUNNING,COMPLETE,FAIL,SKIP'],
            'status' => ['required', 'string', 'in:ok,err,skip,run,warn'],
            'ref' => ['required', 'string', 'max:191'],
            'detail' => ['nullable', 'string', 'max:512'],
            'at' => ['nullable', 'string'],
            'live' => ['nullable', 'boolean'],
        ]);

        if ($validator->fails()) {
            return response()->json([
                'status' => 'error',
                'code' => 'VALIDATION_ERROR',
                'message' => 'Invalid webhook payload',
                'errors' => $validator->errors(),
            ], 422);
        }

        $data = $validator->validated();
        $zoneId = (int) $data['zone_id'];
        $executionId = (string) $data['execution_id'];

        // Защита от "сирот": webhook на несуществующую task игнорируется без 500
        // (history-logger мог сработать быстрее, чем Laravel успел закоммитить task).
        $taskExists = AeTask::query()->where('zone_id', $zoneId)->where('id', (int) $executionId)->exists();
        if (! $taskExists) {
            Log::info('history-logger webhook: ae_task not found, broadcasting step as-is', [
                'zone_id' => $zoneId,
                'execution_id' => $executionId,
                'step' => $data['step'],
            ]);
        }

        $debounceMs = max(0, (int) config('services.history_logger.webhook_debounce_ms', 250));
        if ($debounceMs > 0) {
            $lockKey = sprintf('chain-webhook-debounce:%d:%s:%s', $zoneId, $executionId, $data['step']);
            $lock = Cache::lock($lockKey, max(1, (int) ceil($debounceMs / 1000)));
            if (! $lock->get()) {
                return response()->json([
                    'status' => 'ok',
                    'debounced' => true,
                ]);
            }
        }

        $step = [
            'step' => $data['step'],
            'at' => $data['at'] ?? null,
            'ref' => $data['ref'],
            'detail' => $data['detail'] ?? '',
            'status' => $data['status'],
        ];
        if (array_key_exists('live', $data) && $data['live'] !== null) {
            $step['live'] = (bool) $data['live'];
        }

        ExecutionChainUpdated::dispatch($zoneId, $executionId, $step);

        return response()->json([
            'status' => 'ok',
        ]);
    }
}
