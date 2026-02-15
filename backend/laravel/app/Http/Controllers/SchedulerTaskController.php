<?php

namespace App\Http\Controllers;

use App\Helpers\ZoneAccessHelper;
use App\Models\SchedulerLog;
use App\Models\Zone;
use Illuminate\Http\Client\ConnectionException;
use Illuminate\Http\Client\RequestException;
use Illuminate\Http\Client\Response;
use Illuminate\Http\JsonResponse;
use Illuminate\Http\Request;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Http;
use Illuminate\Support\Facades\Log;
use Illuminate\Support\Facades\Schema;

class SchedulerTaskController extends Controller
{
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

    public function index(Request $request, Zone $zone): JsonResponse
    {
        $this->authorizeZoneAccess($request, $zone);

        $limit = (int) $request->integer('limit', 20);
        $limit = max(1, min($limit, 100));
        $includeTimeline = $request->boolean('include_timeline', false);

        $rows = SchedulerLog::query()
            ->where('task_name', 'like', 'ae_scheduler_task_st-%')
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

        if (! preg_match('/^st-[A-Za-z0-9\-_.:]{6,128}$/', $taskId)) {
            return response()->json([
                'status' => 'error',
                'code' => 'VALIDATION_ERROR',
                'message' => 'Некорректный task_id',
            ], 422);
        }

        $automationTask = null;
        $automationError = null;

        try {
            $automationTask = $this->fetchTaskFromAutomationEngine($taskId);
        } catch (\Throwable $e) {
            $automationError = $e;
            Log::warning('SchedulerTaskController: automation-engine task status unavailable', [
                'task_id' => $taskId,
                'zone_id' => $zone->id,
                'error' => $e->getMessage(),
            ]);
        }

        if (is_array($automationTask)) {
            $taskZoneId = (int) ($automationTask['zone_id'] ?? 0);
            if ($taskZoneId !== (int) $zone->id) {
                return response()->json([
                    'status' => 'error',
                    'code' => 'NOT_FOUND',
                    'message' => 'Task not found for this zone',
                ], 404);
            }

            $lifecycle = $this->buildLifecycle($taskId, $zone->id);
            $payload = $this->normalizeTaskPayload($automationTask, $taskId, 'automation_engine');
            $payload['lifecycle'] = $lifecycle;
            $timeline = $this->buildTaskTimeline(
                $zone->id,
                (string) ($payload['task_id'] ?? $taskId),
                is_string($payload['correlation_id'] ?? null) ? $payload['correlation_id'] : null
            );
            $payload['timeline'] = $timeline;
            $process = $this->buildTaskProcessView($payload, $timeline);
            $payload['process_state'] = $process['process_state'];
            $payload['process_steps'] = $process['process_steps'];

            return response()->json([
                'status' => 'ok',
                'data' => $payload,
            ]);
        }

        if ($automationError instanceof ConnectionException || $automationError instanceof RequestException) {
            return response()->json([
                'status' => 'error',
                'code' => 'UPSTREAM_UNAVAILABLE',
                'message' => 'Automation-engine недоступен.',
            ], 503);
        }

        if ($automationError !== null) {
            return response()->json([
                'status' => 'error',
                'code' => 'UPSTREAM_ERROR',
                'message' => 'Ошибка при получении статуса из automation-engine.',
            ], 503);
        }

        return response()->json([
            'status' => 'error',
            'code' => 'NOT_FOUND',
            'message' => 'Task not found',
        ], 404);
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

    private function fetchTaskFromAutomationEngine(string $taskId): ?array
    {
        $apiUrl = rtrim((string) config('services.automation_engine.api_url', 'http://automation-engine:9405'), '/');
        $timeout = (float) config('services.automation_engine.timeout', 2.0);

        /** @var Response $response */
        $response = Http::acceptJson()->timeout($timeout)->get("{$apiUrl}/scheduler/task/{$taskId}");

        if ($response->status() === 404) {
            return null;
        }

        $response->throw();

        $payload = $response->json();
        if (! is_array($payload)) {
            throw new \RuntimeException('automation_engine_invalid_payload');
        }
        if (($payload['status'] ?? null) !== 'ok') {
            $code = is_string($payload['code'] ?? null) ? $payload['code'] : 'unknown';
            $message = is_string($payload['message'] ?? null) ? $payload['message'] : 'no_message';
            throw new \RuntimeException("automation_engine_non_ok_status: {$code}: {$message}");
        }

        $data = $payload['data'] ?? null;
        if (! is_array($data)) {
            throw new \RuntimeException('automation_engine_missing_data');
        }

        return $data;
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
                ->where('task_name', 'ae_scheduler_task_'.$taskId)
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
                'status' => (string) ($details['status'] ?? $row->status ?? 'unknown'),
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
            if ($taskId === '') {
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
                $process = $this->buildTaskProcessView($payload, []);
                $payload['process_state'] = $process['process_state'];
                $payload['process_steps'] = $process['process_steps'];

                return $payload;
            })
            ->sortByDesc('updated_at')
            ->take($limit)
            ->values()
            ->all();

        if ($includeTimeline) {
            foreach ($items as &$item) {
                $timeline = $this->buildTaskTimeline(
                    $zoneId,
                    (string) ($item['task_id'] ?? ''),
                    is_string($item['correlation_id'] ?? null) ? $item['correlation_id'] : null
                );
                $item['timeline'] = $timeline;
                $process = $this->buildTaskProcessView($item, $timeline);
                $item['process_state'] = $process['process_state'];
                $item['process_steps'] = $process['process_steps'];
            }
            unset($item);
        }

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

    /**
     * @param  array<string,mixed>  $payload
     * @param  array<int, array<string,mixed>>  $timeline
     * @return array{process_state: array<string,mixed>, process_steps: array<int, array<string,mixed>>}
     */
    private function buildTaskProcessView(array $payload, array $timeline): array
    {
        $stepsByPhase = [];
        foreach (self::PROCESS_PHASE_SEQUENCE as $phaseCode) {
            $stepsByPhase[$phaseCode] = [
                'phase' => $phaseCode,
                'label' => self::PROCESS_PHASE_LABELS[$phaseCode] ?? $phaseCode,
                'status' => 'pending',
                'status_label' => $this->processStatusLabel('pending'),
                'started_at' => null,
                'updated_at' => null,
                'last_reason_code' => null,
                'last_event_type' => null,
            ];
        }

        $latestAction = null;
        foreach ($timeline as $event) {
            if (! is_array($event)) {
                continue;
            }

            $eventType = is_string($event['event_type'] ?? null) ? strtoupper(trim($event['event_type'])) : '';
            $reasonCode = is_string($event['reason_code'] ?? null) ? strtolower(trim($event['reason_code'])) : '';
            $runMode = is_string($event['run_mode'] ?? null) ? strtolower(trim($event['run_mode'])) : '';
            $at = $this->toIso8601($event['at'] ?? null);

            $phaseCode = $this->resolveProcessPhaseCode($eventType, $reasonCode, $runMode);
            if ($phaseCode === null || ! isset($stepsByPhase[$phaseCode])) {
                continue;
            }

            if ($at !== null && (
                ! is_array($latestAction)
                || strcmp((string) ($latestAction['at'] ?? ''), $at) <= 0
            )) {
                $latestAction = [
                    'event_type' => $eventType !== '' ? $eventType : null,
                    'reason_code' => $reasonCode !== '' ? $reasonCode : null,
                    'at' => $at,
                ];
            }

            $step = $stepsByPhase[$phaseCode];
            if ($step['started_at'] === null) {
                $step['started_at'] = $at;
            }
            $step['updated_at'] = $at;
            $step['last_reason_code'] = $reasonCode !== '' ? $reasonCode : null;
            $step['last_event_type'] = $eventType !== '' ? $eventType : null;

            $resolvedStatus = $this->resolveProcessStepStatus($eventType, $reasonCode);
            if ($resolvedStatus !== null) {
                $step['status'] = $resolvedStatus;
                $step['status_label'] = $this->processStatusLabel($resolvedStatus);
            } elseif ($step['status'] === 'pending') {
                $step['status'] = 'running';
                $step['status_label'] = $this->processStatusLabel('running');
            }

            $stepsByPhase[$phaseCode] = $step;
        }

        $taskStatus = strtolower(trim((string) ($payload['status'] ?? '')));
        $runMode = strtolower(trim((string) ($payload['run_mode'] ?? (($payload['result']['run_mode'] ?? '')))));
        if (in_array($taskStatus, ['failed', 'rejected', 'expired'], true)) {
            $failedPhase = $this->resolveCurrentPhaseCode($stepsByPhase) ?? 'setup_transition';
            $stepsByPhase[$failedPhase]['status'] = 'failed';
            $stepsByPhase[$failedPhase]['status_label'] = $this->processStatusLabel('failed');
            if ($stepsByPhase[$failedPhase]['updated_at'] === null) {
                $stepsByPhase[$failedPhase]['updated_at'] = $this->toIso8601($payload['updated_at'] ?? null);
            }
        }

        if ($taskStatus === 'completed') {
            if ($runMode === 'working') {
                $setupStep = $stepsByPhase['setup_transition'];
                if ($setupStep['status'] !== 'completed') {
                    $setupStep['status'] = 'completed';
                    $setupStep['status_label'] = $this->processStatusLabel('completed');
                    if ($setupStep['updated_at'] === null) {
                        $setupStep['updated_at'] = $this->toIso8601($payload['updated_at'] ?? null);
                    }
                }
                $stepsByPhase['setup_transition'] = $setupStep;
            }

            foreach (self::PROCESS_PHASE_SEQUENCE as $phaseCode) {
                if ($stepsByPhase[$phaseCode]['status'] === 'running') {
                    $stepsByPhase[$phaseCode]['status'] = 'completed';
                    $stepsByPhase[$phaseCode]['status_label'] = $this->processStatusLabel('completed');
                }
            }
        }

        $currentPhase = $this->resolveCurrentPhaseCode($stepsByPhase);
        $hasFailedStep = collect($stepsByPhase)->contains(static fn (array $step): bool => $step['status'] === 'failed');
        $hasRunningStep = collect($stepsByPhase)->contains(static fn (array $step): bool => $step['status'] === 'running');
        $allCompleted = collect($stepsByPhase)->every(static fn (array $step): bool => $step['status'] === 'completed');

        $processStatus = 'pending';
        if (in_array($taskStatus, ['failed', 'rejected', 'expired'], true) || $hasFailedStep) {
            $processStatus = 'failed';
        } elseif (in_array($taskStatus, ['accepted', 'running'], true) || $hasRunningStep) {
            $processStatus = 'running';
        } elseif ($taskStatus === 'completed' || $allCompleted) {
            $processStatus = 'completed';
        }

        $setupCompleted = $stepsByPhase['setup_transition']['status'] === 'completed';
        $processSteps = [];
        foreach (self::PROCESS_PHASE_SEQUENCE as $phaseCode) {
            $processSteps[] = $stepsByPhase[$phaseCode];
        }

        $processState = [
            'status' => $processStatus,
            'status_label' => $this->processStatusLabel($processStatus),
            'phase' => $currentPhase,
            'phase_label' => $currentPhase !== null ? (self::PROCESS_PHASE_LABELS[$currentPhase] ?? $currentPhase) : null,
            'is_setup_completed' => $setupCompleted,
            'is_work_mode' => $runMode === 'working' || $setupCompleted,
            'current_action' => $latestAction,
        ];

        return [
            'process_state' => $processState,
            'process_steps' => $processSteps,
        ];
    }

    private function resolveProcessPhaseCode(string $eventType, string $reasonCode, string $runMode): ?string
    {
        if ($reasonCode !== '' && in_array($reasonCode, self::PROCESS_CLEAN_FILL_REASON_CODES, true)) {
            return 'clean_fill';
        }
        if ($reasonCode !== '' && in_array($reasonCode, self::PROCESS_SOLUTION_FILL_REASON_CODES, true)) {
            return 'solution_fill';
        }
        if ($reasonCode !== '' && in_array($reasonCode, self::PROCESS_SETUP_TRANSITION_REASON_CODES, true)) {
            return 'setup_transition';
        }
        if ($reasonCode !== '' && in_array($reasonCode, self::PROCESS_PARALLEL_CORRECTION_REASON_CODES, true)) {
            return 'parallel_correction';
        }

        if (in_array($eventType, ['TANK_REFILL_STARTED', 'TANK_REFILL_COMPLETED', 'TANK_REFILL_TIMEOUT'], true)) {
            return 'clean_fill';
        }

        if (in_array($eventType, ['CYCLE_START_INITIATED', 'NODES_AVAILABILITY_CHECKED', 'TANK_LEVEL_CHECKED', 'TANK_LEVEL_STALE'], true)) {
            return 'clean_fill';
        }

        if (in_array($eventType, ['TASK_RECEIVED', 'TASK_STARTED', 'DECISION_MADE'], true)) {
            return 'clean_fill';
        }

        if ($runMode === 'working' && in_array($eventType, ['TASK_FINISHED', 'SCHEDULE_TASK_EXECUTION_FINISHED'], true)) {
            return 'setup_transition';
        }

        return null;
    }

    private function resolveProcessStepStatus(string $eventType, string $reasonCode): ?string
    {
        if (
            $reasonCode !== '' && in_array($reasonCode, self::PROCESS_FAIL_REASON_CODES, true)
            || in_array($eventType, ['TANK_REFILL_TIMEOUT', 'SCHEDULE_TASK_FAILED'], true)
        ) {
            return 'failed';
        }

        if (
            $reasonCode !== '' && in_array($reasonCode, self::PROCESS_SUCCESS_REASON_CODES, true)
            || in_array($eventType, ['TANK_REFILL_COMPLETED', 'TASK_FINISHED', 'SCHEDULE_TASK_COMPLETED', 'SCHEDULE_TASK_EXECUTION_FINISHED'], true)
        ) {
            return 'completed';
        }

        if (
            $reasonCode !== '' && in_array($reasonCode, self::PROCESS_RUNNING_REASON_CODES, true)
            || in_array($eventType, ['TASK_STARTED', 'SCHEDULE_TASK_EXECUTION_STARTED', 'TANK_REFILL_STARTED'], true)
        ) {
            return 'running';
        }

        return null;
    }

    /**
     * @param  array<string, array<string,mixed>>  $stepsByPhase
     */
    private function resolveCurrentPhaseCode(array $stepsByPhase): ?string
    {
        foreach (self::PROCESS_PHASE_SEQUENCE as $phaseCode) {
            if (($stepsByPhase[$phaseCode]['status'] ?? null) === 'running') {
                return $phaseCode;
            }
        }

        foreach (self::PROCESS_PHASE_SEQUENCE as $phaseCode) {
            if (($stepsByPhase[$phaseCode]['status'] ?? null) === 'failed') {
                return $phaseCode;
            }
        }

        $lastCompleted = null;
        foreach (self::PROCESS_PHASE_SEQUENCE as $phaseCode) {
            if (($stepsByPhase[$phaseCode]['status'] ?? null) === 'completed') {
                $lastCompleted = $phaseCode;
            }
        }

        return $lastCompleted;
    }

    private function processStatusLabel(string $status): string
    {
        return match ($status) {
            'running' => 'Выполняется',
            'completed' => 'Выполнено',
            'failed' => 'Ошибка',
            default => 'Ожидание',
        };
    }

    /**
     * @param  array<string,mixed>  $raw
     * @return array<string,mixed>
     */
    private function normalizeTaskPayload(array $raw, string $taskId, string $source): array
    {
        $result = is_array($raw['result'] ?? null) ? $raw['result'] : null;
        $actionRequired = $this->normalizeOptionalBool($raw['action_required'] ?? null);
        if ($actionRequired === null) {
            $actionRequired = $this->normalizeOptionalBool($result['action_required'] ?? null);
        }

        $decision = is_string($raw['decision'] ?? null) ? $raw['decision'] : null;
        if ($decision === null && is_string($result['decision'] ?? null)) {
            $decision = $result['decision'];
        }

        $reasonCode = is_string($raw['reason_code'] ?? null) ? $raw['reason_code'] : null;
        if ($reasonCode === null && is_string($result['reason_code'] ?? null)) {
            $reasonCode = $result['reason_code'];
        }

        $reason = is_string($raw['reason'] ?? null) ? $raw['reason'] : null;
        if ($reason === null && is_string($result['reason'] ?? null)) {
            $reason = $result['reason'];
        }

        $commandSubmitted = $this->normalizeOptionalBool($raw['command_submitted'] ?? null);
        if ($commandSubmitted === null) {
            $commandSubmitted = $this->normalizeOptionalBool($result['command_submitted'] ?? null);
        }

        $commandEffectConfirmed = $this->normalizeOptionalBool($raw['command_effect_confirmed'] ?? null);
        if ($commandEffectConfirmed === null) {
            $commandEffectConfirmed = $this->normalizeOptionalBool($result['command_effect_confirmed'] ?? null);
        }

        $commandsTotal = null;
        if (isset($raw['commands_total']) && is_numeric($raw['commands_total'])) {
            $commandsTotal = (int) $raw['commands_total'];
        } elseif (isset($result['commands_total']) && is_numeric($result['commands_total'])) {
            $commandsTotal = (int) $result['commands_total'];
        }

        $commandsEffectConfirmed = null;
        if (isset($raw['commands_effect_confirmed']) && is_numeric($raw['commands_effect_confirmed'])) {
            $commandsEffectConfirmed = (int) $raw['commands_effect_confirmed'];
        } elseif (isset($result['commands_effect_confirmed']) && is_numeric($result['commands_effect_confirmed'])) {
            $commandsEffectConfirmed = (int) $result['commands_effect_confirmed'];
        }

        $commandsFailed = null;
        if (isset($raw['commands_failed']) && is_numeric($raw['commands_failed'])) {
            $commandsFailed = (int) $raw['commands_failed'];
        } elseif (isset($result['commands_failed']) && is_numeric($result['commands_failed'])) {
            $commandsFailed = (int) $result['commands_failed'];
        }

        $executedSteps = is_array($raw['executed_steps'] ?? null) ? $raw['executed_steps'] : null;
        if ($executedSteps === null && is_array($result['executed_steps'] ?? null)) {
            $executedSteps = $result['executed_steps'];
        }

        $safetyFlags = is_array($raw['safety_flags'] ?? null) ? $raw['safety_flags'] : null;
        if ($safetyFlags === null && is_array($result['safety_flags'] ?? null)) {
            $safetyFlags = $result['safety_flags'];
        }

        $nextDueAt = is_string($raw['next_due_at'] ?? null) ? $raw['next_due_at'] : null;
        if ($nextDueAt === null && is_string($result['next_due_at'] ?? null)) {
            $nextDueAt = $result['next_due_at'];
        }

        $measurementsBeforeAfter = is_array($raw['measurements_before_after'] ?? null)
            ? $raw['measurements_before_after']
            : null;
        if ($measurementsBeforeAfter === null && is_array($result['measurements_before_after'] ?? null)) {
            $measurementsBeforeAfter = $result['measurements_before_after'];
        }

        $runMode = is_string($raw['run_mode'] ?? null) ? $raw['run_mode'] : null;
        if ($runMode === null && is_string($result['run_mode'] ?? null)) {
            $runMode = $result['run_mode'];
        }

        $retryAttempt = $this->normalizeOptionalInt($raw['retry_attempt'] ?? null);
        if ($retryAttempt === null) {
            $retryAttempt = $this->normalizeOptionalInt($result['retry_attempt'] ?? null);
        }

        $retryMaxAttempts = $this->normalizeOptionalInt($raw['retry_max_attempts'] ?? null);
        if ($retryMaxAttempts === null) {
            $retryMaxAttempts = $this->normalizeOptionalInt($result['retry_max_attempts'] ?? null);
        }

        $retryBackoffSec = $this->normalizeOptionalInt($raw['retry_backoff_sec'] ?? null);
        if ($retryBackoffSec === null) {
            $retryBackoffSec = $this->normalizeOptionalInt($result['retry_backoff_sec'] ?? null);
        }

        return [
            'task_id' => (string) ($raw['task_id'] ?? $taskId),
            'zone_id' => isset($raw['zone_id']) ? (int) $raw['zone_id'] : null,
            'task_type' => $raw['task_type'] ?? null,
            'status' => $raw['status'] ?? null,
            'created_at' => $raw['created_at'] ?? null,
            'updated_at' => $raw['updated_at'] ?? null,
            'scheduled_for' => $raw['scheduled_for'] ?? null,
            'due_at' => $raw['due_at'] ?? null,
            'expires_at' => $raw['expires_at'] ?? null,
            'correlation_id' => $raw['correlation_id'] ?? null,
            'result' => $result,
            'action_required' => $actionRequired,
            'decision' => $decision,
            'reason_code' => $reasonCode,
            'reason' => $reason,
            'command_submitted' => $commandSubmitted,
            'command_effect_confirmed' => $commandEffectConfirmed,
            'commands_total' => $commandsTotal,
            'commands_effect_confirmed' => $commandsEffectConfirmed,
            'commands_failed' => $commandsFailed,
            'executed_steps' => $executedSteps,
            'safety_flags' => $safetyFlags,
            'next_due_at' => $nextDueAt,
            'measurements_before_after' => $measurementsBeforeAfter,
            'run_mode' => $runMode,
            'retry_attempt' => $retryAttempt,
            'retry_max_attempts' => $retryMaxAttempts,
            'retry_backoff_sec' => $retryBackoffSec,
            'error' => is_string($raw['error'] ?? null) ? $raw['error'] : null,
            'error_code' => is_string($raw['error_code'] ?? null) ? $raw['error_code'] : null,
            'source' => $source,
        ];
    }

    private function zoneEventPayloadColumn(): string
    {
        return Schema::hasColumn('zone_events', 'payload_json') ? 'payload_json' : 'details';
    }

    /**
     * @param  mixed  $value
     */
    private function toIso8601($value): ?string
    {
        if ($value instanceof \DateTimeInterface) {
            return $value->format(DATE_ATOM);
        }

        if (is_string($value) && $value !== '') {
            try {
                return (new \DateTimeImmutable($value))->format(DATE_ATOM);
            } catch (\Throwable $e) {
                return $value;
            }
        }

        return null;
    }

    /**
     * @param  mixed  $value
     */
    private function normalizeOptionalBool($value): ?bool
    {
        if (is_bool($value)) {
            return $value;
        }
        if (is_int($value)) {
            return $value === 1 ? true : ($value === 0 ? false : null);
        }
        if (is_string($value)) {
            $normalized = strtolower(trim($value));
            if ($normalized === 'true' || $normalized === '1') {
                return true;
            }
            if ($normalized === 'false' || $normalized === '0') {
                return false;
            }
        }

        return null;
    }

    /**
     * @param  mixed  $value
     */
    private function normalizeOptionalInt($value): ?int
    {
        if (is_int($value)) {
            return $value;
        }
        if (is_numeric($value)) {
            return (int) $value;
        }

        return null;
    }

    /**
     * @param  mixed  $rawDetails
     * @return array<string,mixed>
     */
    private function normalizeDetails($rawDetails): array
    {
        if (is_array($rawDetails)) {
            return $rawDetails;
        }

        if (is_string($rawDetails) && $rawDetails !== '') {
            $decoded = json_decode($rawDetails, true);

            return is_array($decoded) ? $decoded : [];
        }

        return [];
    }
}
