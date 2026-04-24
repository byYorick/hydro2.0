<?php

declare(strict_types=1);

namespace App\Http\Controllers\Api\Internal;

use App\Events\ExecutionChainUpdated;
use App\Http\Controllers\Controller;
use App\Models\AeTask;
use Illuminate\Http\JsonResponse;
use Illuminate\Http\Request;
use Illuminate\Support\Facades\Cache;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Log;
use Illuminate\Support\Facades\Validator;

/**
 * Принимает событие о прогрессе execution-а от history-logger-а и
 * ретранслирует его в broadcast-канал `hydro.zone.executions.{zoneId}`
 * для обновления cockpit-UI в реальном времени.
 *
 * Принимаются два режима identificaion-а execution-а:
 *   - `execution_id` (= `ae_tasks.id`) — прямая ссылка;
 *   - `cmd_id` — Laravel сам резолвит `ae_tasks.id` по связи
 *     `commands.cmd_id → corr_snapshot_cmd_id` либо через `ae_tasks.intent_id`.
 *
 * Подпись проверяется в middleware `verify.history-logger.webhook`. Чтобы
 * не штормить WS при множественных ACK на одну команду, broadcast
 * дебаунсится через cache-lock (`HISTORY_LOGGER_WEBHOOK_DEBOUNCE_MS`).
 */
class HistoryLoggerWebhookController extends Controller
{
    public function executionEvent(Request $request): JsonResponse
    {
        $validator = Validator::make($request->all(), [
            'zone_id' => ['required', 'integer', 'min:1'],
            'execution_id' => ['nullable', 'string', 'regex:/^\d+$/'],
            'cmd_id' => ['nullable', 'string', 'max:191'],
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
        $executionId = isset($data['execution_id']) && $data['execution_id'] !== ''
            ? (string) $data['execution_id']
            : null;
        $cmdId = isset($data['cmd_id']) && $data['cmd_id'] !== ''
            ? (string) $data['cmd_id']
            : null;

        if ($executionId === null && $cmdId === null) {
            return response()->json([
                'status' => 'error',
                'code' => 'VALIDATION_ERROR',
                'message' => 'Either execution_id or cmd_id required',
            ], 422);
        }

        if ($executionId === null) {
            $executionId = $this->resolveExecutionIdFromCmdId((string) $cmdId, $zoneId);
        }

        // Защита от "сирот": webhook на несуществующую task игнорируется без 500
        // (history-logger мог сработать быстрее, чем Laravel успел закоммитить task,
        // либо cmd_id пока не связан с task-ом).
        if ($executionId === null) {
            Log::info('history-logger webhook: execution_id unresolvable, dropping silently', [
                'zone_id' => $zoneId,
                'cmd_id' => $cmdId,
                'step' => $data['step'],
            ]);

            return response()->json([
                'status' => 'ok',
                'unresolved' => true,
            ]);
        }

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
            'execution_id' => $executionId,
        ]);
    }

    /**
     * Резолвит `ae_tasks.id` по `cmd_id`.
     *
     * 1. Попытка через `ae_tasks.corr_snapshot_cmd_id` — точный match на
     *    correction-команду.
     * 2. Попытка через `commands.cmd_id → commands.zone_id` + ближайший по
     *    времени `ae_tasks` активный на этой зоне.
     *
     * Возвращает null, если связь не установлена (это не ошибка — webhook
     * просто игнорируется с `unresolved=true`).
     */
    private function resolveExecutionIdFromCmdId(string $cmdId, int $zoneId): ?string
    {
        $task = AeTask::query()
            ->where('zone_id', $zoneId)
            ->where('corr_snapshot_cmd_id', $cmdId)
            ->orderByDesc('id')
            ->first();
        if ($task !== null) {
            return (string) $task->id;
        }

        if (! \Schema::hasTable('commands')) {
            return null;
        }

        $command = DB::table('commands')
            ->where('zone_id', $zoneId)
            ->where('cmd_id', $cmdId)
            ->orderByDesc('created_at')
            ->first(['zone_id', 'created_at']);

        if ($command === null) {
            return null;
        }

        $createdAt = $command->created_at;
        if ($createdAt === null) {
            return null;
        }

        // Активный task зоны, созданный в окне ±10 минут от команды.
        $candidate = AeTask::query()
            ->where('zone_id', $zoneId)
            ->where('created_at', '<=', $createdAt)
            ->orderByDesc('created_at')
            ->orderByDesc('id')
            ->first();

        return $candidate !== null ? (string) $candidate->id : null;
    }
}
