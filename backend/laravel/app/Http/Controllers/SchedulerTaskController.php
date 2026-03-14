<?php

namespace App\Http\Controllers;

use App\Helpers\ZoneAccessHelper;
use App\Http\Controllers\Concerns\BuildsSchedulerTaskProcessView;
use App\Models\SchedulerLog;
use App\Models\Zone;
use Illuminate\Http\JsonResponse;
use Illuminate\Http\Request;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Schema;

class SchedulerTaskController extends Controller
{
    use BuildsSchedulerTaskProcessView;
    private const TASK_ID_PATTERN = '/^(?:\d{1,20}|st-[A-Za-z0-9\-_.:]{6,128})$/';

    private const PROCESS_PHASE_SEQUENCE = [
        'clean_fill',
        'solution_fill',
        'parallel_correction',
        'setup_transition',
    ];

    private const PROCESS_PHASE_LABELS = [
        'clean_fill' => 'Набор бака с чистой водой',
        'solution_fill' => 'Набор бака с раствором',
        'parallel_correction' => 'Параллельная коррекция pH/EC',
        'setup_transition' => 'Завершение setup и переход в рабочий режим',
    ];

    private const PROCESS_CLEAN_FILL_REASON_CODES = [
        'clean_fill_started',
        'clean_fill_in_progress',
        'clean_fill_completed',
        'clean_fill_timeout',
        'clean_fill_retry_started',
        'tank_refill_started',
        'tank_refill_in_progress',
        'tank_refill_completed',
        'tank_refill_timeout',
        'tank_refill_required',
        'tank_refill_not_required',
    ];

    private const PROCESS_SOLUTION_FILL_REASON_CODES = [
        'solution_fill_started',
        'solution_fill_in_progress',
        'solution_fill_completed',
        'solution_fill_timeout',
    ];

    private const PROCESS_PARALLEL_CORRECTION_REASON_CODES = [
        'prepare_recirculation_started',
        'prepare_targets_not_reached',
        'prepare_npk_ph_target_not_reached',
        'tank_to_tank_correction_started',
        'online_correction_failed',
        'irrigation_recovery_started',
        'irrigation_recovery_recovered',
        'irrigation_recovery_failed',
        'irrigation_recovery_degraded',
    ];

    private const PROCESS_SETUP_TRANSITION_REASON_CODES = [
        'prepare_targets_reached',
        'setup_completed',
        'setup_finished',
        'setup_to_working',
        'working_mode_activated',
    ];

    private const PROCESS_FAIL_REASON_CODES = [
        'clean_fill_timeout',
        'solution_fill_timeout',
        'prepare_targets_not_reached',
        'prepare_npk_ph_target_not_reached',
        'online_correction_failed',
        'irrigation_recovery_failed',
        'irrigation_recovery_attempts_exceeded',
        'cycle_start_refill_timeout',
        'task_execution_failed',
        'execution_exception',
    ];

    private const PROCESS_SUCCESS_REASON_CODES = [
        'clean_fill_completed',
        'tank_refill_completed',
        'solution_fill_completed',
        'prepare_targets_reached',
        'irrigation_recovery_recovered',
        'irrigation_recovery_degraded',
        'setup_completed',
        'setup_finished',
        'setup_to_working',
        'working_mode_activated',
    ];

    private const PROCESS_RUNNING_REASON_CODES = [
        'clean_fill_started',
        'clean_fill_in_progress',
        'clean_fill_retry_started',
        'tank_refill_started',
        'tank_refill_in_progress',
        'solution_fill_started',
        'solution_fill_in_progress',
        'prepare_recirculation_started',
        'tank_to_tank_correction_started',
        'irrigation_recovery_started',
    ];

    private const TASK_TIMELINE_EVENT_TYPES = [
        'TASK_RECEIVED',
        'TASK_STARTED',
        'DECISION_MADE',
        'COMMAND_DISPATCHED',
        'COMMAND_FAILED',
        'COMMAND_EFFECT_NOT_CONFIRMED',
        'TASK_FINISHED',
        'SCHEDULE_TASK_ACCEPTED',
        'SCHEDULE_TASK_COMPLETED',
        'SCHEDULE_TASK_FAILED',
        'SCHEDULE_TASK_EXECUTION_STARTED',
        'SCHEDULE_TASK_EXECUTION_FINISHED',
        'DIAGNOSTICS_SERVICE_UNAVAILABLE',
        'SELF_TASK_ENQUEUED',
        'SELF_TASK_DISPATCHED',
        'SELF_TASK_DISPATCH_FAILED',
        'SELF_TASK_EXPIRED',
        'CYCLE_START_INITIATED',
        'NODES_AVAILABILITY_CHECKED',
        'TANK_LEVEL_CHECKED',
        'TANK_LEVEL_STALE',
        'TANK_REFILL_STARTED',
        'TANK_REFILL_COMPLETED',
        'TANK_REFILL_TIMEOUT',
    ];

    private const RUNTIME_ACTIVE_TASK_SELECT = [
        'id',
        'task_id',
        'zone_id',
        'task_type',
        'correlation_id',
        'status',
        'accepted_at',
        'due_at',
        'expires_at',
        'last_polled_at',
        'terminal_at',
        'details',
        'created_at',
        'updated_at',
    ];

    private const RUNTIME_INTENT_SELECT = [
        'id',
        'zone_id',
        'intent_type',
        'idempotency_key',
        'status',
        'claimed_at',
        'completed_at',
        'error_code',
        'error_message',
        'retry_count',
        'max_retries',
        'payload',
        'created_at',
        'updated_at',
    ];

    private const RUNTIME_AE_TASK_SELECT = [
        'id',
        'zone_id',
        'task_type',
        'status',
        'idempotency_key',
        'intent_id',
        'intent_source',
        'current_stage',
        'workflow_phase',
        'corr_step',
        'error_code',
        'error_message',
        'scheduled_for',
        'due_at',
        'created_at',
        'updated_at',
        'completed_at',
    ];

    public function index(Request $request, Zone $zone): JsonResponse
    {
        $this->authorizeZoneAccess($request, $zone);

        $limit = (int) $request->integer('limit', 20);
        $limit = max(1, min($limit, 100));
        $includeTimeline = $request->boolean('include_timeline', false);

        $rows = SchedulerLog::query()
            ->whereRaw("jsonb_exists(details, 'task_id')")
            ->whereRaw("jsonb_exists(details, 'zone_id') AND (details->>'zone_id') ~ '^[0-9]+$' AND (details->>'zone_id')::int = ?", [$zone->id])
            ->orderByDesc('created_at')
            ->orderByDesc('id')
            ->limit(max(200, $limit * 10))
            ->get(['id', 'task_name', 'status', 'details', 'created_at']);

        $tasks = $this->aggregateTaskRows($rows, $limit, $zone->id, $includeTimeline);

        return response()->json([
            'status' => 'ok',
            'data' => $tasks,
        ]);
    }

    public function show(Request $request, Zone $zone, string $taskId): JsonResponse
    {
        $this->authorizeZoneAccess($request, $zone);

        if (! preg_match(self::TASK_ID_PATTERN, $taskId)) {
            return response()->json([
                'status' => 'error',
                'code' => 'VALIDATION_ERROR',
                'message' => 'Некорректный task_id',
            ], 422);
        }

        $rows = SchedulerLog::query()
            ->where(function ($query) use ($taskId): void {
                $query
                    ->whereRaw("details->>'task_id' = ?", [$taskId])
                    ->orWhere('task_name', 'ae_scheduler_task_'.$taskId);
            })
            ->whereRaw("jsonb_exists(details, 'zone_id') AND (details->>'zone_id') ~ '^[0-9]+$' AND (details->>'zone_id')::int = ?", [$zone->id])
            ->orderBy('created_at')
            ->orderBy('id')
            ->get(['id', 'status', 'details', 'created_at']);

        if ($rows->isEmpty()) {
            return response()->json([
                'status' => 'error',
                'code' => 'NOT_FOUND',
                'message' => 'Task not found',
            ], 404);
        }

        /** @var SchedulerLog $lastRow */
        $lastRow = $rows->last();
        $payload = $this->normalizeTaskPayload($this->normalizeDetails($lastRow->details), $taskId, 'scheduler_logs');
        $runtimeContext = $this->buildTaskRuntimeContext(
            $zone->id,
            (string) ($payload['task_id'] ?? $taskId),
            is_string($payload['correlation_id'] ?? null) ? $payload['correlation_id'] : null
        );
        $payload = $this->enrichPayloadWithRuntimeContext($payload, $runtimeContext);
        $payload['lifecycle'] = $this->buildLifecycle($taskId, $zone->id, $rows);
        $timeline = $this->buildTaskTimeline(
            $zone->id,
            (string) ($payload['task_id'] ?? $taskId),
            is_string($payload['correlation_id'] ?? null) ? $payload['correlation_id'] : null
        );
        if ($timeline === []) {
            $timeline = $this->buildTaskTimelineFromSchedulerRows(
                $rows,
                (string) ($payload['task_id'] ?? $taskId),
                is_string($payload['correlation_id'] ?? null) ? $payload['correlation_id'] : null
            );
        }
        $payload['timeline'] = $timeline;
        $process = $this->buildTaskProcessView($payload, $timeline, $runtimeContext);
        $payload['process_state'] = $process['process_state'];
        $payload['process_steps'] = $process['process_steps'];

        return response()->json([
            'status' => 'ok',
            'data' => $payload,
        ]);
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

    /**
     * @param  \Illuminate\Support\Collection<int, SchedulerLog>|null  $preparedRows
     * @return array<int, array<string,mixed>>
     */
    private function buildLifecycle(string $taskId, int $zoneId, $preparedRows = null): array
    {
        $rows = $preparedRows;
        if ($rows === null) {
            $rows = SchedulerLog::query()
                ->where(function ($query) use ($taskId): void {
                    $query
                        ->whereRaw("details->>'task_id' = ?", [$taskId])
                        ->orWhere('task_name', 'ae_scheduler_task_'.$taskId);
                })
                ->whereRaw("jsonb_exists(details, 'zone_id') AND (details->>'zone_id') ~ '^[0-9]+$' AND (details->>'zone_id')::int = ?", [$zoneId])
                ->orderBy('created_at')
                ->orderBy('id')
                ->get(['id', 'status', 'details', 'created_at']);
        } else {
            $rows = $rows
                ->sort(static function (SchedulerLog $left, SchedulerLog $right): int {
                    $leftAt = (string) ($left->created_at?->toIso8601String() ?? '');
                    $rightAt = (string) ($right->created_at?->toIso8601String() ?? '');
                    $createdAtCompare = strcmp($leftAt, $rightAt);
                    if ($createdAtCompare !== 0) {
                        return $createdAtCompare;
                    }

                    return (int) ($left->id ?? 0) <=> (int) ($right->id ?? 0);
                })
                ->values();
        }

        return $rows->map(function (SchedulerLog $row): array {
            $details = $this->normalizeDetails($row->details);

            return [
                'status' => $this->normalizeSchedulerTaskStatus($details['status'] ?? $row->status ?? 'unknown'),
                'at' => $row->created_at?->toIso8601String(),
                'error' => $details['error'] ?? null,
                'source' => 'scheduler_logs',
            ];
        })->all();
    }

    /**
     * @param  \Illuminate\Support\Collection<int, SchedulerLog>  $rows
     * @return array<int, array<string,mixed>>
     */
    private function aggregateTaskRows($rows, int $limit, int $zoneId, bool $includeTimeline = false): array
    {
        $bucket = [];

        foreach ($rows as $row) {
            $details = $this->normalizeDetails($row->details);
            $taskId = (string) ($details['task_id'] ?? str_replace('ae_scheduler_task_', '', (string) $row->task_name));
            if ($taskId === '' || preg_match(self::TASK_ID_PATTERN, $taskId) !== 1) {
                continue;
            }

            if (! isset($bucket[$taskId])) {
                $bucket[$taskId] = [
                    'payload' => $this->normalizeTaskPayload($details, $taskId, 'scheduler_logs'),
                    'updated_at' => $row->created_at,
                    'updated_id' => (int) ($row->id ?? 0),
                    'lifecycle' => [],
                ];
            }

            $rowId = (int) ($row->id ?? 0);
            $bucket[$taskId]['lifecycle'][] = [
                'status' => (string) ($details['status'] ?? $row->status ?? 'unknown'),
                'at' => $row->created_at?->toIso8601String(),
                'error' => $details['error'] ?? null,
                'source' => 'scheduler_logs',
                '_row_id' => $rowId,
            ];

            $isNewerTimestamp = $row->created_at && $bucket[$taskId]['updated_at'] && $row->created_at->gt($bucket[$taskId]['updated_at']);
            $isSameTimestampButNewerId = $row->created_at
                && $bucket[$taskId]['updated_at']
                && $row->created_at->equalTo($bucket[$taskId]['updated_at'])
                && $rowId > (int) ($bucket[$taskId]['updated_id'] ?? 0);

            if ($isNewerTimestamp || $isSameTimestampButNewerId) {
                $bucket[$taskId]['payload'] = $this->normalizeTaskPayload($details, $taskId, 'scheduler_logs');
                $bucket[$taskId]['updated_at'] = $row->created_at;
                $bucket[$taskId]['updated_id'] = $rowId;
            }
        }

        $items = collect($bucket)
            ->map(function (array $entry): array {
                usort($entry['lifecycle'], static function (array $a, array $b): int {
                    $timestampCompare = strcmp((string) ($a['at'] ?? ''), (string) ($b['at'] ?? ''));
                    if ($timestampCompare !== 0) {
                        return $timestampCompare;
                    }

                    return (int) ($a['_row_id'] ?? 0) <=> (int) ($b['_row_id'] ?? 0);
                });
                $entry['lifecycle'] = array_map(static function (array $item): array {
                    unset($item['_row_id']);

                    return $item;
                }, $entry['lifecycle']);

                $payload = $entry['payload'];
                $payload['lifecycle'] = $entry['lifecycle'];
                $payload['timeline'] = [];

                return $payload;
            })
            ->sortByDesc('updated_at')
            ->take($limit)
            ->values()
            ->all();

        foreach ($items as &$item) {
            $runtimeContext = $this->buildTaskRuntimeContext(
                $zoneId,
                (string) ($item['task_id'] ?? ''),
                is_string($item['correlation_id'] ?? null) ? $item['correlation_id'] : null
            );
            $item = $this->enrichPayloadWithRuntimeContext($item, $runtimeContext);

            $timeline = [];
            if ($includeTimeline) {
                $timeline = $this->buildTaskTimeline(
                    $zoneId,
                    (string) ($item['task_id'] ?? ''),
                    is_string($item['correlation_id'] ?? null) ? $item['correlation_id'] : null
                );
                if ($timeline === []) {
                    $timeline = $this->buildTaskTimelineFromLifecycle($item);
                }
            }

            $item['timeline'] = $timeline;
            $process = $this->buildTaskProcessView($item, $timeline, $runtimeContext);
            $item['process_state'] = $process['process_state'];
            $item['process_steps'] = $process['process_steps'];
        }
        unset($item);

        return $items;
    }

    /**
     * @return array<int, array<string,mixed>>
     */
    private function buildTaskTimeline(int $zoneId, string $taskId, ?string $correlationId, int $limit = 200): array
    {
        $normalizedTaskId = trim($taskId);
        $normalizedCorrelationId = is_string($correlationId) ? trim($correlationId) : '';
        if ($normalizedTaskId === '' && $normalizedCorrelationId === '') {
            return [];
        }

        $payloadColumn = $this->zoneEventPayloadColumn();
        $safeLimit = max(1, min($limit, 500));

        $rows = DB::table('zone_events')
            ->where('zone_id', $zoneId)
            ->whereIn('type', self::TASK_TIMELINE_EVENT_TYPES)
            ->where(function ($query) use ($payloadColumn, $normalizedTaskId, $normalizedCorrelationId): void {
                if ($normalizedTaskId !== '') {
                    $query->whereRaw("{$payloadColumn}->>'task_id' = ?", [$normalizedTaskId]);
                }

                if ($normalizedCorrelationId !== '') {
                    $method = $normalizedTaskId !== '' ? 'orWhereRaw' : 'whereRaw';
                    $query->{$method}("{$payloadColumn}->>'correlation_id' = ?", [$normalizedCorrelationId]);
                }
            })
            ->orderBy('created_at')
            ->orderBy('id')
            ->limit($safeLimit)
            ->get([
                'id',
                'type',
                DB::raw("{$payloadColumn} as details"),
                'created_at',
            ]);

        return $rows->map(function ($row) use ($normalizedTaskId, $normalizedCorrelationId): array {
            $details = $this->normalizeDetails($row->details ?? null);
            $result = is_array($details['result'] ?? null) ? $details['result'] : [];
            $eventType = is_string($details['event_type'] ?? null) && $details['event_type'] !== ''
                ? $details['event_type']
                : (string) ($row->type ?? 'unknown');

            $eventSeq = null;
            if (isset($details['event_seq']) && is_numeric($details['event_seq'])) {
                $eventSeq = (int) $details['event_seq'];
            }

            $eventIdRaw = $details['event_id'] ?? $details['ws_event_id'] ?? $row->id;
            $actionRequired = $this->normalizeOptionalBool($details['action_required'] ?? null);
            if ($actionRequired === null) {
                $actionRequired = $this->normalizeOptionalBool($result['action_required'] ?? null);
            }

            $decision = is_string($details['decision'] ?? null) ? $details['decision'] : null;
            if ($decision === null && is_string($result['decision'] ?? null)) {
                $decision = $result['decision'];
            }

            $reasonCode = is_string($details['reason_code'] ?? null) ? $details['reason_code'] : null;
            if ($reasonCode === null && is_string($result['reason_code'] ?? null)) {
                $reasonCode = $result['reason_code'];
            }

            $reason = is_string($details['reason'] ?? null) ? $details['reason'] : null;
            if ($reason === null && is_string($result['reason'] ?? null)) {
                $reason = $result['reason'];
            }

            $errorCode = is_string($details['error_code'] ?? null) ? $details['error_code'] : null;
            if ($errorCode === null && is_string($result['error_code'] ?? null)) {
                $errorCode = $result['error_code'];
            }

            $commandSubmitted = $this->normalizeOptionalBool($details['command_submitted'] ?? null);
            if ($commandSubmitted === null) {
                $commandSubmitted = $this->normalizeOptionalBool($result['command_submitted'] ?? null);
            }

            $commandEffectConfirmed = $this->normalizeOptionalBool($details['command_effect_confirmed'] ?? null);
            if ($commandEffectConfirmed === null) {
                $commandEffectConfirmed = $this->normalizeOptionalBool($result['command_effect_confirmed'] ?? null);
            }

            $executedSteps = is_array($details['executed_steps'] ?? null) ? $details['executed_steps'] : null;
            if ($executedSteps === null && is_array($result['executed_steps'] ?? null)) {
                $executedSteps = $result['executed_steps'];
            }

            $safetyFlags = is_array($details['safety_flags'] ?? null) ? $details['safety_flags'] : null;
            if ($safetyFlags === null && is_array($result['safety_flags'] ?? null)) {
                $safetyFlags = $result['safety_flags'];
            }

            $nextDueAt = is_string($details['next_due_at'] ?? null) ? $details['next_due_at'] : null;
            if ($nextDueAt === null && is_string($result['next_due_at'] ?? null)) {
                $nextDueAt = $result['next_due_at'];
            }

            $measurementsBeforeAfter = is_array($details['measurements_before_after'] ?? null)
                ? $details['measurements_before_after']
                : null;
            if ($measurementsBeforeAfter === null && is_array($result['measurements_before_after'] ?? null)) {
                $measurementsBeforeAfter = $result['measurements_before_after'];
            }

            $runMode = is_string($details['run_mode'] ?? null) ? $details['run_mode'] : null;
            if ($runMode === null && is_string($result['run_mode'] ?? null)) {
                $runMode = $result['run_mode'];
            }

            $retryAttempt = $this->normalizeOptionalInt($details['retry_attempt'] ?? null);
            if ($retryAttempt === null) {
                $retryAttempt = $this->normalizeOptionalInt($result['retry_attempt'] ?? null);
            }

            $retryMaxAttempts = $this->normalizeOptionalInt($details['retry_max_attempts'] ?? null);
            if ($retryMaxAttempts === null) {
                $retryMaxAttempts = $this->normalizeOptionalInt($result['retry_max_attempts'] ?? null);
            }

            $retryBackoffSec = $this->normalizeOptionalInt($details['retry_backoff_sec'] ?? null);
            if ($retryBackoffSec === null) {
                $retryBackoffSec = $this->normalizeOptionalInt($result['retry_backoff_sec'] ?? null);
            }

            return [
                'event_id' => (string) $eventIdRaw,
                'event_seq' => $eventSeq,
                'event_type' => $eventType,
                'type' => (string) ($row->type ?? $eventType),
                'at' => $this->toIso8601($row->created_at ?? null),
                'task_id' => is_string($details['task_id'] ?? null) ? $details['task_id'] : $normalizedTaskId,
                'correlation_id' => is_string($details['correlation_id'] ?? null) ? $details['correlation_id'] : ($normalizedCorrelationId !== '' ? $normalizedCorrelationId : null),
                'task_type' => is_string($details['task_type'] ?? null) ? $details['task_type'] : null,
                'action_required' => $actionRequired,
                'decision' => $decision,
                'reason_code' => $reasonCode,
                'reason' => $reason,
                'node_uid' => is_string($details['node_uid'] ?? null) ? $details['node_uid'] : null,
                'channel' => is_string($details['channel'] ?? null) ? $details['channel'] : null,
                'cmd' => is_string($details['cmd'] ?? null) ? $details['cmd'] : null,
                'status' => is_string($details['status'] ?? null) ? $details['status'] : null,
                'error_code' => $errorCode,
                'command_submitted' => $commandSubmitted,
                'command_effect_confirmed' => $commandEffectConfirmed,
                'executed_steps' => $executedSteps,
                'safety_flags' => $safetyFlags,
                'next_due_at' => $nextDueAt,
                'measurements_before_after' => $measurementsBeforeAfter,
                'run_mode' => $runMode,
                'retry_attempt' => $retryAttempt,
                'retry_max_attempts' => $retryMaxAttempts,
                'retry_backoff_sec' => $retryBackoffSec,
                'terminal_status' => is_string($details['terminal_status'] ?? null) ? $details['terminal_status'] : null,
                'details' => $details,
                'source' => 'zone_events',
            ];
        })->values()->all();
    }

    private function zoneEventPayloadColumn(): string
    {
        return Schema::hasColumn('zone_events', 'payload_json') ? 'payload_json' : 'details';
    }

    /**
     * @param  \Illuminate\Support\Collection<int, SchedulerLog>  $rows
     * @return array<int, array<string,mixed>>
     */
    private function buildTaskTimelineFromSchedulerRows($rows, string $taskId, ?string $correlationId): array
    {
        $normalizedTaskId = trim($taskId);
        $normalizedCorrelationId = is_string($correlationId) ? trim($correlationId) : '';

        return $rows
            ->values()
            ->map(function (SchedulerLog $row, int $index) use ($normalizedTaskId, $normalizedCorrelationId): array {
                $details = $this->normalizeDetails($row->details);
                $status = $this->normalizeSchedulerTaskStatus($details['status'] ?? $row->status ?? 'unknown');
                $eventType = $this->schedulerStatusToFallbackEventType($status);
                $reasonCode = is_string($details['reason_code'] ?? null) ? $details['reason_code'] : null;
                if ($reasonCode === null) {
                    $reasonCode = is_string($details['result']['reason_code'] ?? null)
                        ? $details['result']['reason_code']
                        : $this->schedulerStatusToFallbackReasonCode($status);
                }

                $resolvedTaskId = is_string($details['task_id'] ?? null) && trim($details['task_id']) !== ''
                    ? trim($details['task_id'])
                    : $normalizedTaskId;
                $resolvedCorrelationId = is_string($details['correlation_id'] ?? null) && trim($details['correlation_id']) !== ''
                    ? trim($details['correlation_id'])
                    : ($normalizedCorrelationId !== '' ? $normalizedCorrelationId : null);

                return [
                    'event_id' => 'scheduler-log-'.$row->id.'-'.$index,
                    'event_seq' => $index + 1,
                    'event_type' => $eventType,
                    'type' => $eventType,
                    'at' => $this->toIso8601($row->created_at ?? null),
                    'task_id' => $resolvedTaskId,
                    'correlation_id' => $resolvedCorrelationId,
                    'task_type' => is_string($details['task_type'] ?? null) ? $details['task_type'] : null,
                    'status' => $status,
                    'reason_code' => $reasonCode,
                    'reason' => is_string($details['reason'] ?? null) ? $details['reason'] : null,
                    'run_mode' => is_string($details['run_mode'] ?? null) ? $details['run_mode'] : null,
                    'details' => $details,
                    'source' => 'scheduler_logs_fallback',
                ];
            })
            ->all();
    }

    /**
     * @param  array<string,mixed>  $payload
     * @return array<int, array<string,mixed>>
     */
    private function buildTaskTimelineFromLifecycle(array $payload): array
    {
        $lifecycle = is_array($payload['lifecycle'] ?? null) ? $payload['lifecycle'] : [];
        if ($lifecycle === []) {
            return [];
        }

        $taskId = is_string($payload['task_id'] ?? null) ? trim((string) $payload['task_id']) : '';
        $correlationId = is_string($payload['correlation_id'] ?? null) ? trim((string) $payload['correlation_id']) : '';

        return collect($lifecycle)
            ->values()
            ->map(function ($item, int $index) use ($taskId, $correlationId): array {
                $eventPayload = is_array($item) ? $item : [];
                $status = $this->normalizeSchedulerTaskStatus($eventPayload['status'] ?? 'unknown');
                $eventType = $this->schedulerStatusToFallbackEventType($status);
                $reasonCode = $this->schedulerStatusToFallbackReasonCode($status);

                return [
                    'event_id' => 'lifecycle-'.$taskId.'-'.$index,
                    'event_seq' => $index + 1,
                    'event_type' => $eventType,
                    'type' => $eventType,
                    'at' => $this->toIso8601($eventPayload['at'] ?? null),
                    'task_id' => $taskId !== '' ? $taskId : null,
                    'correlation_id' => $correlationId !== '' ? $correlationId : null,
                    'status' => $status,
                    'reason_code' => $reasonCode,
                    'reason' => is_string($eventPayload['error'] ?? null) ? $eventPayload['error'] : null,
                    'details' => $eventPayload,
                    'source' => 'scheduler_logs_lifecycle_fallback',
                ];
            })
            ->all();
    }

    /**
     * @return array{
     *   active_task: array<string,mixed>|null,
     *   intent: array<string,mixed>|null,
     *   ae_task: array<string,mixed>|null,
     *   stage_transitions: array<int, array<string,mixed>>,
     *   current_stage: string|null,
     *   workflow_phase: string|null,
     *   corr_step: string|null,
     *   updated_at: string|null
     * }
     */
    private function buildTaskRuntimeContext(int $zoneId, string $taskId, ?string $correlationId): array
    {
        $normalizedTaskId = trim($taskId);
        $normalizedCorrelationId = is_string($correlationId) ? trim($correlationId) : '';

        $activeTask = $this->loadActiveTaskSnapshot($zoneId, $normalizedTaskId, $normalizedCorrelationId);
        if ($normalizedCorrelationId === '' && is_string($activeTask['correlation_id'] ?? null)) {
            $normalizedCorrelationId = trim($activeTask['correlation_id']);
        }

        $intentId = $this->extractIntentIdFromActiveTask($activeTask);
        $intent = $this->loadIntentSnapshot($zoneId, $intentId, $normalizedCorrelationId);
        if ($intent !== null) {
            $intentId = isset($intent['id']) && is_numeric($intent['id']) ? (int) $intent['id'] : $intentId;
            if ($normalizedCorrelationId === '' && is_string($intent['idempotency_key'] ?? null)) {
                $normalizedCorrelationId = trim($intent['idempotency_key']);
            }
        }

        $aeTask = $this->loadAeTaskSnapshot($zoneId, $normalizedTaskId, $intentId, $normalizedCorrelationId);
        if ($intent === null && isset($aeTask['intent_id']) && is_numeric($aeTask['intent_id'])) {
            $resolvedIntentId = (int) $aeTask['intent_id'];
            if ($resolvedIntentId > 0) {
                $intent = $this->loadIntentSnapshot($zoneId, $resolvedIntentId, $normalizedCorrelationId);
                if ($intent !== null) {
                    $intentId = $resolvedIntentId;
                }
            }
        }

        $stageTransitions = [];
        if ($aeTask !== null && isset($aeTask['id']) && is_numeric($aeTask['id'])) {
            $stageTransitions = $this->loadAeStageTransitions((int) $aeTask['id']);
        }

        $currentStage = is_string($aeTask['current_stage'] ?? null)
            ? strtolower(trim($aeTask['current_stage']))
            : null;
        $workflowPhase = is_string($aeTask['workflow_phase'] ?? null)
            ? strtolower(trim($aeTask['workflow_phase']))
            : null;
        $corrStep = is_string($aeTask['corr_step'] ?? null)
            ? strtolower(trim($aeTask['corr_step']))
            : null;

        return [
            'active_task' => $activeTask,
            'intent' => $intent,
            'ae_task' => $aeTask,
            'stage_transitions' => $stageTransitions,
            'current_stage' => $currentStage !== '' ? $currentStage : null,
            'workflow_phase' => $workflowPhase !== '' ? $workflowPhase : null,
            'corr_step' => $corrStep !== '' ? $corrStep : null,
            'updated_at' => $aeTask['updated_at']
                ?? $activeTask['updated_at']
                ?? $intent['updated_at']
                ?? null,
        ];
    }

    /**
     * @param  array<string,mixed>  $payload
     * @param  array<string,mixed>  $runtimeContext
     * @return array<string,mixed>
     */
    private function enrichPayloadWithRuntimeContext(array $payload, array $runtimeContext): array
    {
        $activeTask = is_array($runtimeContext['active_task'] ?? null) ? $runtimeContext['active_task'] : [];
        $intent = is_array($runtimeContext['intent'] ?? null) ? $runtimeContext['intent'] : [];
        $aeTask = is_array($runtimeContext['ae_task'] ?? null) ? $runtimeContext['ae_task'] : [];

        $statusCandidates = [
            $this->normalizeSchedulerRuntimeStatus($aeTask['status'] ?? null),
            $this->normalizeSchedulerRuntimeStatus($activeTask['status'] ?? null),
            $this->normalizeSchedulerRuntimeStatus($intent['status'] ?? null),
            $this->normalizeSchedulerRuntimeStatus($payload['status'] ?? null),
        ];
        foreach ($statusCandidates as $statusCandidate) {
            if ($statusCandidate !== null) {
                $payload['status'] = $statusCandidate;
                break;
            }
        }

        if (($payload['task_type'] ?? null) === null) {
            $payload['task_type'] = $activeTask['task_type']
                ?? $aeTask['task_type']
                ?? $intent['intent_type']
                ?? null;
        }

        if (! is_string($payload['correlation_id'] ?? null) || trim((string) $payload['correlation_id']) === '') {
            $payload['correlation_id'] = $activeTask['correlation_id']
                ?? $intent['idempotency_key']
                ?? $aeTask['idempotency_key']
                ?? null;
        }

        if (! is_string($payload['created_at'] ?? null) || trim((string) $payload['created_at']) === '') {
            $payload['created_at'] = $this->toIso8601(
                $activeTask['accepted_at']
                ?? $intent['created_at']
                ?? $aeTask['created_at']
                ?? null
            );
        }

        if (! is_string($payload['updated_at'] ?? null) || trim((string) $payload['updated_at']) === '') {
            $payload['updated_at'] = $this->toIso8601(
                $aeTask['updated_at']
                ?? $activeTask['terminal_at']
                ?? $activeTask['last_polled_at']
                ?? $activeTask['updated_at']
                ?? $intent['completed_at']
                ?? $intent['updated_at']
                ?? null
            );
        }

        if (! is_string($payload['due_at'] ?? null) || trim((string) $payload['due_at']) === '') {
            $payload['due_at'] = $this->toIso8601($activeTask['due_at'] ?? $aeTask['due_at'] ?? null);
        }

        if (! is_string($payload['scheduled_for'] ?? null) || trim((string) $payload['scheduled_for']) === '') {
            $payload['scheduled_for'] = $this->toIso8601($aeTask['scheduled_for'] ?? null);
        }

        if (! is_string($payload['expires_at'] ?? null) || trim((string) $payload['expires_at']) === '') {
            $payload['expires_at'] = $this->toIso8601($activeTask['expires_at'] ?? null);
        }

        if (! is_string($payload['error_code'] ?? null) || trim((string) $payload['error_code']) === '') {
            $payload['error_code'] = $aeTask['error_code']
                ?? $intent['error_code']
                ?? null;
        }

        if (! is_string($payload['error'] ?? null) || trim((string) $payload['error']) === '') {
            $payload['error'] = $aeTask['error_message']
                ?? $intent['error_message']
                ?? null;
        }

        $normalizedStatus = strtolower(trim((string) ($payload['status'] ?? '')));
        $normalizedReasonCode = strtolower(trim((string) ($payload['reason_code'] ?? '')));
        if ($normalizedReasonCode === '') {
            if ($normalizedStatus === 'completed' && $this->runtimeIndicatesSetupCompleted($runtimeContext)) {
                $payload['reason_code'] = 'setup_completed';
            } elseif (in_array($normalizedStatus, ['failed', 'rejected', 'expired'], true)) {
                $payload['reason_code'] = 'task_execution_failed';
            }
        }

        if ((! is_string($payload['reason'] ?? null) || trim((string) $payload['reason']) === '')
            && in_array($normalizedStatus, ['failed', 'rejected', 'expired'], true)
        ) {
            $payload['reason'] = is_string($payload['error_code'] ?? null) ? $payload['error_code'] : null;
        }

        $runMode = strtolower(trim((string) ($payload['run_mode'] ?? '')));
        if ($runMode === '') {
            if ($this->runtimeIndicatesSetupCompleted($runtimeContext)) {
                $payload['run_mode'] = 'working';
            } elseif (is_string($runtimeContext['workflow_phase'] ?? null) && trim($runtimeContext['workflow_phase']) !== '') {
                $payload['run_mode'] = 'setup';
            }
        }

        return $payload;
    }

    private function loadActiveTaskSnapshot(int $zoneId, string $taskId, string $correlationId): ?array
    {
        if (! Schema::hasTable('laravel_scheduler_active_tasks')) {
            return null;
        }
        if ($taskId === '' && $correlationId === '') {
            return null;
        }

        $query = DB::table('laravel_scheduler_active_tasks')
            ->where('zone_id', $zoneId)
            ->where(function ($q) use ($taskId, $correlationId): void {
                if ($taskId !== '') {
                    $q->where('task_id', $taskId);
                }
                if ($correlationId !== '') {
                    $method = $taskId !== '' ? 'orWhere' : 'where';
                    $q->{$method}('correlation_id', $correlationId);
                }
            })
            ->orderByDesc('updated_at')
            ->orderByDesc('id');

        $row = $query->first(self::RUNTIME_ACTIVE_TASK_SELECT);
        if ($row === null) {
            return null;
        }

        $normalized = $this->normalizeDbRow($row);
        $normalized['details'] = $this->normalizeDetails($normalized['details'] ?? null);

        return $normalized;
    }

    private function loadIntentSnapshot(int $zoneId, ?int $intentId, string $correlationId): ?array
    {
        if (! Schema::hasTable('zone_automation_intents')) {
            return null;
        }
        if (($intentId ?? 0) <= 0 && $correlationId === '') {
            return null;
        }

        $query = DB::table('zone_automation_intents')
            ->where('zone_id', $zoneId)
            ->where(function ($q) use ($intentId, $correlationId): void {
                if (($intentId ?? 0) > 0) {
                    $q->where('id', $intentId);
                }
                if ($correlationId !== '') {
                    $method = ($intentId ?? 0) > 0 ? 'orWhere' : 'where';
                    $q->{$method}('idempotency_key', $correlationId);
                }
            })
            ->orderByDesc('updated_at')
            ->orderByDesc('id');

        $row = $query->first(self::RUNTIME_INTENT_SELECT);
        if ($row === null) {
            return null;
        }

        $normalized = $this->normalizeDbRow($row);
        $normalized['payload'] = $this->normalizeDetails($normalized['payload'] ?? null);

        return $normalized;
    }

    private function loadAeTaskSnapshot(int $zoneId, string $taskId, ?int $intentId, string $correlationId): ?array
    {
        if (! Schema::hasTable('ae_tasks')) {
            return null;
        }

        $numericTaskId = ctype_digit($taskId) ? (int) $taskId : null;
        if ($numericTaskId !== null && $numericTaskId > 0) {
            $row = DB::table('ae_tasks')
                ->where('zone_id', $zoneId)
                ->where('id', $numericTaskId)
                ->first(self::RUNTIME_AE_TASK_SELECT);
            if ($row !== null) {
                return $this->normalizeDbRow($row);
            }
        }

        if (($intentId ?? 0) > 0) {
            $row = DB::table('ae_tasks')
                ->where('zone_id', $zoneId)
                ->where('intent_id', $intentId)
                ->orderByDesc('updated_at')
                ->orderByDesc('id')
                ->first(self::RUNTIME_AE_TASK_SELECT);
            if ($row !== null) {
                return $this->normalizeDbRow($row);
            }
        }

        if ($correlationId !== '') {
            $row = DB::table('ae_tasks')
                ->where('zone_id', $zoneId)
                ->where('idempotency_key', $correlationId)
                ->orderByDesc('updated_at')
                ->orderByDesc('id')
                ->first(self::RUNTIME_AE_TASK_SELECT);
            if ($row !== null) {
                return $this->normalizeDbRow($row);
            }
        }

        return null;
    }

    /**
     * @return array<int, array<string,mixed>>
     */
    private function loadAeStageTransitions(int $aeTaskId): array
    {
        if ($aeTaskId <= 0 || ! Schema::hasTable('ae_stage_transitions')) {
            return [];
        }

        $rows = DB::table('ae_stage_transitions')
            ->where('task_id', $aeTaskId)
            ->orderBy('triggered_at')
            ->orderBy('id')
            ->get(['from_stage', 'to_stage', 'workflow_phase', 'triggered_at', 'metadata']);

        return $rows->map(function ($row): array {
            $normalized = $this->normalizeDbRow($row);

            return [
                'from_stage' => is_string($normalized['from_stage'] ?? null)
                    ? strtolower(trim($normalized['from_stage']))
                    : null,
                'to_stage' => is_string($normalized['to_stage'] ?? null)
                    ? strtolower(trim($normalized['to_stage']))
                    : null,
                'workflow_phase' => is_string($normalized['workflow_phase'] ?? null)
                    ? strtolower(trim($normalized['workflow_phase']))
                    : null,
                'at' => $this->toIso8601($normalized['triggered_at'] ?? null),
                'metadata' => $this->normalizeDetails($normalized['metadata'] ?? null),
            ];
        })->all();
    }

    /**
     * @param  array<string,mixed>|null  $activeTask
     */
    private function extractIntentIdFromActiveTask(?array $activeTask): ?int
    {
        if (! is_array($activeTask)) {
            return null;
        }

        $details = is_array($activeTask['details'] ?? null) ? $activeTask['details'] : [];
        $value = $details['intent_id'] ?? null;
        if (! is_numeric($value)) {
            return null;
        }

        $intentId = (int) $value;

        return $intentId > 0 ? $intentId : null;
    }

    /**
     * @param  mixed  $row
     * @return array<string,mixed>
     */
    private function normalizeDbRow($row): array
    {
        if (is_array($row)) {
            return $row;
        }
        if (is_object($row)) {
            /** @var array<string,mixed> $normalized */
            $normalized = get_object_vars($row);

            return $normalized;
        }

        return [];
    }

    /**
     * @param  mixed  $status
     */
    private function normalizeSchedulerRuntimeStatus($status): ?string
    {
        $normalized = $this->normalizeSchedulerTaskStatus($status);
        if ($normalized === 'waiting_command') {
            return 'running';
        }
        if ($normalized === 'unknown' || $normalized === '') {
            return null;
        }

        return $normalized;
    }

    private function schedulerStatusToFallbackEventType(string $status): string
    {
        return match ($status) {
            'completed' => 'TASK_FINISHED',
            'failed', 'rejected', 'expired' => 'SCHEDULE_TASK_FAILED',
            default => 'TASK_STARTED',
        };
    }

    private function schedulerStatusToFallbackReasonCode(string $status): ?string
    {
        return match ($status) {
            'completed' => 'setup_completed',
            'failed', 'rejected', 'expired' => 'task_execution_failed',
            default => 'clean_fill_started',
        };
    }
}
