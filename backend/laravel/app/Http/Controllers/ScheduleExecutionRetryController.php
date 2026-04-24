<?php

declare(strict_types=1);

namespace App\Http\Controllers;

use App\Helpers\ZoneAccessHelper;
use App\Models\AeTask;
use App\Models\Zone;
use App\Services\ZoneAutomationIntentService;
use Carbon\CarbonImmutable;
use Illuminate\Http\JsonResponse;
use Illuminate\Http\Request;

/**
 * Повторный запуск failed execution (AE3 task) из Scheduler Cockpit UI.
 *
 * Создаёт новый `zone_automation_intent` с идемпотентным ключом
 * `retry-{original_task_id}-{timestamp}`. AE3 создаст новый task из этого
 * intent-а и начнёт исполнение.
 *
 * Поддерживается только irrigation_start (в v1). Retry разрешён только
 * для terminal-failed task-ов, чтобы не конфликтовать с активным
 * исполнением (partial unique index `ae_tasks_active_zone_unique`).
 */
class ScheduleExecutionRetryController extends Controller
{
    public function __construct(
        private readonly ZoneAutomationIntentService $intents,
    ) {}

    public function retry(Request $request, Zone $zone, string $executionId): JsonResponse
    {
        $this->authorizeZoneAccess($request, $zone);

        if (preg_match('/^\d+$/', trim($executionId)) !== 1) {
            return response()->json([
                'status' => 'error',
                'code' => 'VALIDATION_ERROR',
                'message' => 'Некорректный execution_id',
            ], 422);
        }

        /** @var AeTask|null $task */
        $task = AeTask::query()
            ->where('zone_id', $zone->id)
            ->where('id', (int) $executionId)
            ->first();

        if ($task === null) {
            return response()->json([
                'status' => 'error',
                'code' => 'NOT_FOUND',
                'message' => 'Execution not found',
            ], 404);
        }

        $status = strtolower((string) $task->status);
        if (! in_array($status, ['failed', 'cancelled'], true)) {
            return response()->json([
                'status' => 'error',
                'code' => 'INVALID_STATE',
                'message' => sprintf(
                    'Retry разрешён только для failed/cancelled execution (текущий статус: %s)',
                    $status,
                ),
            ], 409);
        }

        if ($task->task_type !== 'irrigation_start') {
            return response()->json([
                'status' => 'error',
                'code' => 'UNSUPPORTED_TASK_TYPE',
                'message' => sprintf(
                    'Retry поддерживается только для irrigation_start (получен: %s)',
                    $task->task_type,
                ),
            ], 422);
        }

        $idempotencyKey = sprintf(
            'retry-%d-%s',
            (int) $task->id,
            CarbonImmutable::now('UTC')->format('YmdHisv'),
        );

        $mode = $task->irrigation_mode === 'force' ? 'force' : 'normal';
        $durationSec = $task->irrigation_requested_duration_sec !== null
            ? (int) $task->irrigation_requested_duration_sec
            : null;

        $intentId = $this->intents->upsertStartIrrigationIntent(
            zoneId: $zone->id,
            source: 'scheduler_cockpit_retry',
            idempotencyKey: $idempotencyKey,
            mode: $mode,
            requestedDurationSec: $durationSec,
        );

        if ($intentId === null) {
            return response()->json([
                'status' => 'error',
                'code' => 'INTENT_CONFLICT',
                'message' => 'Не удалось создать intent для retry (возможно, уже существует активный intent для зоны)',
            ], 409);
        }

        return response()->json([
            'status' => 'ok',
            'data' => [
                'intent_id' => $intentId,
                'idempotency_key' => $idempotencyKey,
                'retry_of_execution_id' => (string) $task->id,
            ],
        ], 201);
    }

    private function authorizeZoneAccess(Request $request, Zone $zone): void
    {
        $user = $request->user();
        if (! $user) {
            abort(401, 'Unauthorized');
        }

        if (! ZoneAccessHelper::canAccessZone($user, $zone)) {
            abort(403, 'Forbidden: Access denied to this zone');
        }
    }
}
