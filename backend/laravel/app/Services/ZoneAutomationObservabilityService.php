<?php

namespace App\Services;

use Illuminate\Support\Carbon;
use Illuminate\Support\Facades\DB;

class ZoneAutomationObservabilityService
{
    private const ACTIVE_TASK_STATUSES = ['pending', 'claimed', 'running', 'waiting_command'];

    /** @var list<string> */
    private const CORRECTION_SKIP_EVENT_TYPES = [
        'CORRECTION_SKIPPED_COOLDOWN',
        'CORRECTION_SKIPPED_DOSE_DISCARDED',
        'CORRECTION_SKIPPED_FRESHNESS',
        'CORRECTION_SKIPPED_WINDOW_NOT_READY',
        'CORRECTION_SKIPPED_WATER_LEVEL',
        'CORRECTION_SKIPPED_DEAD_ZONE',
        'CORRECTION_SKIPPED_EMERGENCY_STOP',
        'CORRECTION_SKIPPED_BY_ALERT_BLOCK',
        'CORRECTION_ACTION_DEFERRED',
        'CORRECTION_NO_EFFECT',
        'CORRECTION_PLANNER_CONFIG_INVALID',
        'EC_BATCH_PARTIAL_FAILURE',
        'CORRECTION_EXHAUSTED',
        'PUMP_CALIBRATION_MIRROR_MISMATCH',
    ];

    /** Skip/readiness older than this are ignored for the dosing card (seconds). */
    private const CORRECTION_EVENT_MAX_AGE_SEC = 1800;

    /** @var list<string> */
    private const CORRECTION_READINESS_EVENT_TYPES = [
        'CORRECTION_COMPLETE',
        'CORRECTION_INTERRUPTED_STAGE_COMPLETE',
    ];

    private const TIMELINE_MAX_EVENTS = 12;

    private const TIMELINE_MAX_AGE_SEC = 86400;

    /**
     * Workflow-oriented zone_events used when AE3/Laravel timeline is empty.
     *
     * @var list<string>
     */
    private const TIMELINE_EVENT_TYPES = [
        'SCHEDULE_TASK_ACCEPTED',
        'SCHEDULE_TASK_COMPLETED',
        'SCHEDULE_TASK_FAILED',
        'SCHEDULE_TASK_EXECUTION_STARTED',
        'SCHEDULE_TASK_EXECUTION_FINISHED',
        'TASK_RECEIVED',
        'TASK_STARTED',
        'TASK_FINISHED',
        'AE_TASK_STARTED',
        'AE_TASK_COMPLETED',
        'AE_TASK_FAILED',
        'DECISION_MADE',
        'COMMAND_DISPATCHED',
        'COMMAND_FAILED',
        'COMMAND_EFFECT_NOT_CONFIRMED',
        'CLEAN_FILL_COMPLETED',
        'CLEAN_FILL_RETRY_STARTED',
        'CLEAN_FILL_STARTED',
        'CLEAN_FILL_IN_PROGRESS',
        'CLEAN_FILL_TIMEOUT',
        'CLEAN_FILL_SOURCE_EMPTY',
        'SOLUTION_FILL_COMPLETED',
        'SOLUTION_FILL_STARTED',
        'SOLUTION_FILL_IN_PROGRESS',
        'SOLUTION_FILL_TIMEOUT',
        'SOLUTION_FILL_LEAK_DETECTED',
        'SOLUTION_FILL_CORRECTION',
        'PREPARE_TARGETS_REACHED',
        'PREPARE_TARGETS_NOT_REACHED',
        'TWO_TANK_STARTUP_INITIATED',
        'AUTOMATION_CONTROL_MODE_UPDATED',
        'MANUAL_STEP_ACCEPTED',
        'MANUAL_STEP_REQUESTED',
        'MANUAL_STEP_EXECUTED',
        'WORKFLOW_RECOVERY_STALE_STOPPED',
        'WORKFLOW_RECOVERY_ENQUEUED',
        'WORKFLOW_RECOVERY_WORKFLOW_FALLBACK',
        'LEVEL_SWITCH_CHANGED',
        'CORRECTION_SKIPPED_COOLDOWN',
        'CORRECTION_SKIPPED_DOSE_DISCARDED',
        'CORRECTION_SKIPPED_FRESHNESS',
        'CORRECTION_SKIPPED_WINDOW_NOT_READY',
        'CORRECTION_SKIPPED_WATER_LEVEL',
        'CORRECTION_SKIPPED_DEAD_ZONE',
        'CORRECTION_SKIPPED_EMERGENCY_STOP',
        'CORRECTION_SKIPPED_BY_ALERT_BLOCK',
        'CORRECTION_ACTION_DEFERRED',
        'CORRECTION_NO_EFFECT',
        'CORRECTION_COMPLETE',
        'CORRECTION_EXHAUSTED',
        'CORRECTION_INTERRUPTED_STAGE_COMPLETE',
        'EC_BATCH_PARTIAL_FAILURE',
    ];

    /**
     * Human labels for timeline backfill (frontend may re-map known codes).
     *
     * @var array<string, string>
     */
    private const TIMELINE_EVENT_LABELS = [
        'SCHEDULE_TASK_ACCEPTED' => 'Scheduler: задача принята',
        'SCHEDULE_TASK_COMPLETED' => 'Scheduler: задача завершена',
        'SCHEDULE_TASK_FAILED' => 'Scheduler: задача с ошибкой',
        'SCHEDULE_TASK_EXECUTION_STARTED' => 'Automation-engine: запуск выполнения',
        'SCHEDULE_TASK_EXECUTION_FINISHED' => 'Automation-engine: выполнение завершено',
        'TASK_RECEIVED' => 'Automation-engine: задача получена',
        'TASK_STARTED' => 'Automation-engine: выполнение начато',
        'TASK_FINISHED' => 'Automation-engine: выполнение завершена',
        'AE_TASK_STARTED' => 'Automation-engine: задача начата',
        'AE_TASK_COMPLETED' => 'Automation-engine: задача завершена',
        'AE_TASK_FAILED' => 'Automation-engine: задача с ошибкой',
        'DECISION_MADE' => 'Automation-engine: решение принято',
        'COMMAND_DISPATCHED' => 'Команда отправлена узлу',
        'COMMAND_FAILED' => 'Ошибка отправки команды',
        'COMMAND_EFFECT_NOT_CONFIRMED' => 'Эффект команды не подтверждён',
        'CLEAN_FILL_COMPLETED' => 'Бак чистой воды заполнен',
        'CLEAN_FILL_RETRY_STARTED' => 'Запущен повторный цикл clean-fill',
        'CLEAN_FILL_STARTED' => 'Запущено наполнение бака чистой воды',
        'CLEAN_FILL_IN_PROGRESS' => 'Идёт наполнение бака чистой воды',
        'CLEAN_FILL_TIMEOUT' => 'Таймаут набора чистой воды',
        'CLEAN_FILL_SOURCE_EMPTY' => 'Источник чистой воды пуст',
        'SOLUTION_FILL_COMPLETED' => 'Бак рабочего раствора заполнен',
        'SOLUTION_FILL_STARTED' => 'Запущено наполнение бака раствора',
        'SOLUTION_FILL_IN_PROGRESS' => 'Идёт наполнение бака раствора',
        'SOLUTION_FILL_TIMEOUT' => 'Таймаут набора бака раствора',
        'SOLUTION_FILL_LEAK_DETECTED' => 'Обнаружена утечка раствора',
        'SOLUTION_FILL_CORRECTION' => 'Коррекция раствора при наполнении',
        'PREPARE_TARGETS_REACHED' => 'Целевые pH/EC достигнуты',
        'PREPARE_TARGETS_NOT_REACHED' => 'Цели pH/EC не достигнуты',
        'TWO_TANK_STARTUP_INITIATED' => 'Запущен старт 2-баковой схемы',
        'AUTOMATION_CONTROL_MODE_UPDATED' => 'Режим управления автоматикой обновлён',
        'MANUAL_STEP_ACCEPTED' => 'Ручной шаг принят',
        'MANUAL_STEP_REQUESTED' => 'Запрошен ручной шаг',
        'MANUAL_STEP_EXECUTED' => 'Ручной шаг выполнен',
        'WORKFLOW_RECOVERY_STALE_STOPPED' => 'Залипшая фаза сброшена (авто-восстановление)',
        'WORKFLOW_RECOVERY_ENQUEUED' => 'Workflow возобновлён после рестарта AE',
        'WORKFLOW_RECOVERY_WORKFLOW_FALLBACK' => 'Workflow переключён на резервный',
        'LEVEL_SWITCH_CHANGED' => 'Изменение датчика уровня',
        'CORRECTION_SKIPPED_COOLDOWN' => 'Коррекция пропущена: кулдаун',
        'CORRECTION_SKIPPED_DOSE_DISCARDED' => 'Коррекция пропущена: доза отброшена',
        'CORRECTION_SKIPPED_FRESHNESS' => 'Коррекция пропущена: устаревшая телеметрия',
        'CORRECTION_SKIPPED_WINDOW_NOT_READY' => 'Коррекция пропущена: окно не готово',
        'CORRECTION_SKIPPED_WATER_LEVEL' => 'Коррекция пропущена: уровень воды',
        'CORRECTION_SKIPPED_DEAD_ZONE' => 'Коррекция пропущена: мёртвая зона',
        'CORRECTION_SKIPPED_EMERGENCY_STOP' => 'Коррекция пропущена: E-STOP',
        'CORRECTION_SKIPPED_BY_ALERT_BLOCK' => 'Коррекция пропущена: блок алерта',
        'CORRECTION_ACTION_DEFERRED' => 'Коррекция отложена',
        'CORRECTION_NO_EFFECT' => 'Коррекция без эффекта',
        'CORRECTION_COMPLETE' => 'Коррекция завершена',
        'CORRECTION_EXHAUSTED' => 'Коррекция исчерпана',
        'CORRECTION_INTERRUPTED_STAGE_COMPLETE' => 'Коррекция прервана: этап завершён',
        'EC_BATCH_PARTIAL_FAILURE' => 'Частичный сбой EC-дозы',
    ];

    public function __construct(
        private readonly ObservabilityThresholdRegistry $thresholds,
    ) {}

    /**
     * @param  array<string,mixed>  $payload
     * @return array<string,mixed>
     */
    public function enrichPayload(int $zoneId, array $payload, bool $isStale = false): array
    {
        $rawObservability = is_array($payload['observability'] ?? null) ? $payload['observability'] : null;
        $fromAeLive = $rawObservability !== null
            && ! $isStale
            && (($rawObservability['runtime']['source'] ?? null) !== 'laravel_db_fallback');

        $observability = $rawObservability ?? $this->buildFallbackObservability($zoneId, $payload);

        $observability['scheduler'] = $this->buildSchedulerContext($zoneId);

        if ($isStale) {
            $observability['runtime'] = $this->buildRuntimeFromDatabase($zoneId, $payload, preferDatabaseTiming: true);
            $observability['nodes'] = $this->buildNodesContext($zoneId);
            $hangHints = [];
        } else {
            if (! is_array($observability['runtime'] ?? null) || $observability['runtime'] === []) {
                $observability['runtime'] = $this->buildRuntimeFromDatabase($zoneId, $payload);
            }

            if (! is_array($observability['nodes'] ?? null) || ($observability['nodes']['nodes'] ?? []) === []) {
                $observability['nodes'] = $this->buildNodesContext($zoneId);
            }

            $hangHints = is_array($observability['hang_hints'] ?? null)
                ? $observability['hang_hints']
                : [];
        }

        foreach ($this->schedulerHangHints($observability['scheduler']) as $hint) {
            $hangHints[] = $hint;
        }

        foreach ($this->intentDriftHangHints($zoneId) as $hint) {
            $hangHints[] = $hint;
        }

        foreach ($this->databaseHangHints($zoneId, $observability) as $hint) {
            $hangHints[] = $hint;
        }

        if ($isStale || ! $fromAeLive) {
            foreach ($this->runtimeHangHints($observability['runtime'] ?? []) as $hint) {
                $hangHints[] = $hint;
            }
        }

        $observability['hang_hints'] = $this->dedupeHangHints($hangHints);
        $observability['overall_health'] = $this->resolveOverallHealth(
            $observability['hang_hints'],
            is_array($observability['runtime'] ?? null) ? $observability['runtime'] : [],
        );
        $runtimeTaskId = null;
        if (is_array($observability['runtime'] ?? null) && isset($observability['runtime']['task_id'])) {
            $runtimeTaskId = (int) $observability['runtime']['task_id'];
            if ($runtimeTaskId <= 0) {
                $runtimeTaskId = null;
            }
        }
        $observability['correction'] = $this->buildCorrectionContext($zoneId, $runtimeTaskId);

        $payload['observability'] = $observability;
        $payload = $this->backfillTimelineIfEmpty($zoneId, $payload);

        return $payload;
    }

    /**
     * When AE3/Laravel did not supply timeline events, fill from recent zone_events.
     * Never overwrites a non-empty timeline.
     *
     * @param  array<string,mixed>  $payload
     * @return array<string,mixed>
     */
    private function backfillTimelineIfEmpty(int $zoneId, array $payload): array
    {
        $timeline = $payload['timeline'] ?? null;
        if (is_array($timeline) && $timeline !== []) {
            return $payload;
        }

        $payload['timeline'] = $this->buildTimelineFromZoneEvents($zoneId);

        return $payload;
    }

    /**
     * @return list<array{event: string, timestamp: string, label: string, active: bool}>
     */
    private function buildTimelineFromZoneEvents(int $zoneId): array
    {
        if (! DB::getSchemaBuilder()->hasTable('zone_events')) {
            return [];
        }

        $placeholders = implode(',', array_fill(0, count(self::TIMELINE_EVENT_TYPES), '?'));
        $minCreatedAt = Carbon::now()->subSeconds(self::TIMELINE_MAX_AGE_SEC);
        $bindings = array_merge([$zoneId], self::TIMELINE_EVENT_TYPES, [$minCreatedAt, self::TIMELINE_MAX_EVENTS]);

        $rows = DB::select(
            "SELECT id, type, payload_json, created_at
             FROM zone_events
             WHERE zone_id = ?
               AND type IN ({$placeholders})
               AND created_at >= ?
             ORDER BY id DESC
             LIMIT ?",
            $bindings,
        );

        if ($rows === []) {
            return [];
        }

        $rows = array_reverse($rows);
        $events = [];

        foreach ($rows as $row) {
            $type = is_string($row->type ?? null) ? strtoupper(trim((string) $row->type)) : '';
            if ($type === '') {
                continue;
            }

            $createdAt = $row->created_at ?? null;
            $timestamp = $createdAt !== null
                ? Carbon::parse((string) $createdAt)->toIso8601String()
                : Carbon::now()->toIso8601String();

            $eventPayload = $this->decodeZoneEventPayload($row->payload_json ?? null);
            $labelFromPayload = null;
            if (isset($eventPayload['message']) && is_string($eventPayload['message']) && trim($eventPayload['message']) !== '') {
                $labelFromPayload = trim($eventPayload['message']);
            } elseif (isset($eventPayload['label']) && is_string($eventPayload['label']) && trim($eventPayload['label']) !== '') {
                $labelFromPayload = trim($eventPayload['label']);
            }

            $events[] = [
                'event' => $type,
                'timestamp' => $timestamp,
                'label' => $labelFromPayload ?? (self::TIMELINE_EVENT_LABELS[$type] ?? $type),
                'active' => false,
            ];
        }

        if ($events !== []) {
            $events[array_key_last($events)]['active'] = true;
        }

        return $events;
    }

    /**
     * @param  array<string,mixed>  $payload
     * @return array<string,mixed>
     */
    private function buildFallbackObservability(int $zoneId, array $payload): array
    {
        return [
            'runtime' => $this->buildRuntimeFromDatabase($zoneId, $payload),
            'nodes' => $this->buildNodesContext($zoneId),
            'hang_hints' => [],
            'overall_health' => 'idle',
        ];
    }

    /**
     * @param  array<string,mixed>  $payload
     * @return array<string,mixed>
     */
    private function buildRuntimeFromDatabase(int $zoneId, array $payload, bool $preferDatabaseTiming = false): array
    {
        $task = $this->fetchActiveTaskRow($zoneId);
        $workflow = $this->fetchWorkflowRow($zoneId);
        $stateDetails = is_array($payload['state_details'] ?? null) ? $payload['state_details'] : [];

        $status = is_string($task->status ?? null) ? strtolower((string) $task->status) : null;
        $taskIsActive = $status !== null && in_array($status, self::ACTIVE_TASK_STATUSES, true);

        $currentStage = is_string($payload['current_stage'] ?? null)
            ? (string) $payload['current_stage']
            : (is_string($task->current_stage ?? null) ? (string) $task->current_stage : null);

        if (($currentStage === null || $currentStage === '') && $workflow !== null && is_array($workflow->payload ?? null)) {
            $payloadStage = $workflow->payload['ae3_cycle_start_stage'] ?? null;
            if (is_string($payloadStage) && trim($payloadStage) !== '') {
                $currentStage = trim($payloadStage);
            }
        }

        $workflowPhase = is_string($payload['workflow_phase'] ?? null)
            ? strtolower((string) $payload['workflow_phase'])
            : (is_string($task->workflow_phase ?? null)
                ? strtolower((string) $task->workflow_phase)
                : ($workflow !== null && is_string($workflow->workflow_phase ?? null)
                    ? strtolower((string) $workflow->workflow_phase)
                    : 'idle'));

        if (
            $workflow !== null
            && is_array($workflow->payload ?? null)
            && ($workflow->payload['ae3_failure_rollback'] ?? false)
            && in_array($workflowPhase, ['ready', 'irrig_recirc'], true)
        ) {
            $currentStage = 'complete_ready';
        }

        if (
            $workflow !== null
            && is_array($workflow->payload ?? null)
            && ($workflow->payload['ae3_failure_rollback'] ?? false)
            && $workflowPhase === 'idle'
        ) {
            $currentStage = null;
        }

        $stageEnteredAt = $task->stage_entered_at ?? ($workflow !== null ? $workflow->updated_at : null);
        $stageElapsedSec = 0;
        if ($stageEnteredAt !== null) {
            $stageElapsedSec = max(0, Carbon::parse((string) $stageEnteredAt)->diffInSeconds(now()));
        }

        $taskUpdatedAgeSec = null;
        if ($task->updated_at ?? null) {
            $taskUpdatedAgeSec = max(0, Carbon::parse((string) $task->updated_at)->diffInSeconds(now()));
        }

        $workflowSnapshotAgeSec = null;
        if ($workflow !== null && ($workflow->updated_at ?? null)) {
            $workflowSnapshotAgeSec = max(0, Carbon::parse((string) $workflow->updated_at)->diffInSeconds(now()));
        }

        $stageDeadlineRemainingSec = null;
        if ($task->stage_deadline_at ?? null) {
            // AE3 contract: remaining = deadline - now (positive while deadline is still ahead).
            $stageDeadlineRemainingSec = now()->diffInSeconds(
                Carbon::parse((string) $task->stage_deadline_at),
                false
            );
        }

        $resolvedStageElapsedSec = $preferDatabaseTiming
            ? $stageElapsedSec
            : (int) ($stateDetails['elapsed_sec'] ?? $stageElapsedSec);

        return [
            'zone_id' => $zoneId,
            'task_id' => isset($task->id) ? (int) $task->id : null,
            'task_status' => $status,
            'task_is_active' => $taskIsActive,
            'current_stage' => $currentStage,
            'workflow_phase' => $workflowPhase,
            'stage_entered_at' => $stageEnteredAt ? Carbon::parse((string) $stageEnteredAt)->toIso8601String() : null,
            'stage_elapsed_sec' => $resolvedStageElapsedSec,
            'stage_deadline_at' => ($task->stage_deadline_at ?? null)
                ? Carbon::parse((string) $task->stage_deadline_at)->toIso8601String()
                : null,
            'stage_deadline_remaining_sec' => $stageDeadlineRemainingSec,
            'waiting_command' => $status === 'waiting_command',
            'waiting_elapsed_sec' => $status === 'waiting_command' ? ($taskUpdatedAgeSec ?? $stageElapsedSec) : 0,
            'task_updated_age_sec' => $taskUpdatedAgeSec,
            'correction_step' => is_string($task->corr_step ?? null) ? (string) $task->corr_step : null,
            'pending_manual_step' => is_string($task->pending_manual_step ?? null) ? (string) $task->pending_manual_step : null,
            'topology' => is_string($task->topology ?? null) ? (string) $task->topology : null,
            'workflow_snapshot_updated_at' => ($workflow !== null && ($workflow->updated_at ?? null))
                ? Carbon::parse((string) $workflow->updated_at)->toIso8601String()
                : null,
            'workflow_snapshot_age_sec' => $workflowSnapshotAgeSec,
            'source' => 'laravel_db_fallback',
        ];
    }

    /**
     * @return object{
     *     id?:int,
     *     status?:string,
     *     current_stage?:string,
     *     workflow_phase?:string,
     *     stage_entered_at?:string,
     *     stage_deadline_at?:string,
     *     updated_at?:string,
     *     corr_step?:string,
     *     pending_manual_step?:string,
     *     topology?:string
     * }
     */
    private function fetchActiveTaskRow(int $zoneId): object
    {
        $placeholders = implode(',', array_fill(0, count(self::ACTIVE_TASK_STATUSES), '?'));

        $row = DB::selectOne(
            "SELECT id, status, current_stage, workflow_phase, stage_entered_at, stage_deadline_at,
                    updated_at, corr_step, pending_manual_step, topology
             FROM ae_tasks
             WHERE zone_id = ?
               AND status IN ({$placeholders})
             ORDER BY updated_at DESC, id DESC
             LIMIT 1",
            array_merge([$zoneId], self::ACTIVE_TASK_STATUSES),
        );

        if ($row !== null) {
            return $row;
        }

        return DB::selectOne(
            'SELECT id, status, current_stage, workflow_phase, stage_entered_at, stage_deadline_at,
                    updated_at, corr_step, pending_manual_step, topology
             FROM ae_tasks
             WHERE zone_id = ?
             ORDER BY updated_at DESC, id DESC
             LIMIT 1',
            [$zoneId],
        ) ?? (object) [];
    }

    /**
     * @return object{workflow_phase?:string,updated_at?:string,payload?:array<string,mixed>}|null
     */
    private function fetchWorkflowRow(int $zoneId): ?object
    {
        $row = DB::selectOne(
            'SELECT workflow_phase, updated_at, payload FROM zone_workflow_state WHERE zone_id = ? LIMIT 1',
            [$zoneId],
        );

        if ($row === null) {
            return null;
        }

        if (is_string($row->payload ?? null)) {
            $decoded = json_decode((string) $row->payload, true);
            $row->payload = is_array($decoded) ? $decoded : [];
        } elseif (! is_array($row->payload ?? null)) {
            $row->payload = [];
        }

        return $row;
    }

    /**
     * @return array<string,mixed>
     */
    private function buildNodesContext(int $zoneId): array
    {
        $rows = DB::select(
            "SELECT
                n.uid AS node_uid,
                LOWER(COALESCE(n.type, '')) AS node_type,
                LOWER(TRIM(COALESCE(n.status, ''))) AS status,
                EXTRACT(
                    EPOCH FROM (
                        NOW() - COALESCE(n.last_seen_at, n.last_heartbeat_at, n.updated_at)
                    )
                )::BIGINT AS last_seen_age_sec
             FROM nodes n
             WHERE n.zone_id = ?
             ORDER BY n.id ASC",
            [$zoneId],
        );

        $requiredTypes = ['irrig', 'ph', 'ec'];
        $nodes = [];
        $offlineRequired = [];
        $persistentOffline = false;

        foreach ($rows as $row) {
            $type = strtolower((string) ($row->node_type ?? ''));
            $uid = (string) ($row->node_uid ?? '');
            $status = strtolower((string) ($row->status ?? ''));
            $age = isset($row->last_seen_age_sec) ? (int) $row->last_seen_age_sec : null;
            $isOnline = $status === 'online';
            $isStaleOnline = $isOnline && $age !== null && $age >= $this->thresholds->int('nodes_stale_online_sec', 120);
            $required = in_array($type, $requiredTypes, true);

            $nodes[] = [
                'uid' => $uid !== '' ? $uid : null,
                'type' => $type !== '' ? $type : null,
                'status' => $status !== '' ? $status : null,
                'last_seen_age_sec' => $age,
                'required' => $required,
                'healthy' => $isOnline && ! $isStaleOnline,
            ];

            if ($required && (! $isOnline || $isStaleOnline)) {
                $offlineRequired[] = $uid !== '' ? $uid : $type;
                if (! $isOnline && $age !== null && $age >= $this->thresholds->int('nodes_persistent_offline_sec', 600)) {
                    $persistentOffline = true;
                }
            }
        }

        return [
            'nodes' => $nodes,
            'offline_required' => $offlineRequired,
            'persistent_offline' => $persistentOffline,
        ];
    }

    /**
     * @return array<string,mixed>
     */
    private function buildSchedulerContext(int $zoneId): array
    {
        $pendingIntents = DB::table('zone_automation_intents')
            ->where('zone_id', $zoneId)
            ->whereIn('status', ['pending', 'claimed', 'running'])
            ->orderByDesc('created_at')
            ->limit(5)
            ->get([
                'id',
                'status',
                'intent_type',
                'not_before',
                'created_at',
                'updated_at',
                'claimed_at',
            ]);

        $latest = $pendingIntents->first();
        $now = Carbon::now();

        $pendingAgeSec = null;
        if ($latest !== null) {
            $status = (string) ($latest->status ?? '');
            $anchor = match ($status) {
                'pending' => $latest->created_at ?? $latest->updated_at,
                'claimed' => $latest->claimed_at ?? $latest->updated_at ?? $latest->created_at,
                default => $latest->updated_at ?? $latest->created_at,
            };
            if ($anchor !== null) {
                $pendingAgeSec = max(0, Carbon::parse((string) $anchor)->diffInSeconds($now));
            }
        }

        return [
            'pending_count' => $pendingIntents->where('status', 'pending')->count(),
            'active_count' => $pendingIntents->count(),
            'latest_intent' => $latest === null ? null : [
                'id' => (int) $latest->id,
                'status' => (string) $latest->status,
                'intent_type' => (string) ($latest->intent_type ?? ''),
                'not_before' => $latest->not_before ? Carbon::parse((string) $latest->not_before)->toIso8601String() : null,
                'created_at' => $latest->created_at ? Carbon::parse((string) $latest->created_at)->toIso8601String() : null,
                'updated_at' => $latest->updated_at ? Carbon::parse((string) $latest->updated_at)->toIso8601String() : null,
                'age_sec' => $pendingAgeSec,
            ],
        ];
    }

    /**
     * @param  array<string,mixed>  $scheduler
     * @return list<array<string,mixed>>
     */
    private function schedulerHangHints(array $scheduler): array
    {
        $latest = is_array($scheduler['latest_intent'] ?? null) ? $scheduler['latest_intent'] : null;
        if ($latest === null) {
            return [];
        }

        $status = (string) ($latest['status'] ?? '');
        $ageSec = (int) ($latest['age_sec'] ?? 0);

        if ($status === 'pending' && $ageSec >= $this->thresholds->int('scheduler_intent_pending_warn_sec', 300)) {
            return [[
                'code' => 'scheduler_intent_pending',
                'severity' => $ageSec >= $this->thresholds->int('scheduler_intent_pending_critical_sec', 900) ? 'critical' : 'warning',
                'message' => 'Intent планировщика ожидает исполнения дольше ожидаемого',
                'recommendation' => 'Проверьте Laravel scheduler-dispatch, wake-up AE3 и логи automation-engine.',
                'details' => [
                    'intent_id' => $latest['id'] ?? null,
                    'intent_type' => $latest['intent_type'] ?? null,
                    'age_sec' => $ageSec,
                ],
            ]];
        }

        if ($status === 'claimed' && $ageSec >= $this->thresholds->int('scheduler_intent_claimed_warn_sec', 180)) {
            return [[
                'code' => 'scheduler_intent_claimed_stuck',
                'severity' => $ageSec >= $this->thresholds->int('scheduler_intent_claimed_critical_sec', 600) ? 'critical' : 'warning',
                'message' => 'Intent захвачен, но не перешёл в running',
                'recommendation' => 'Проверьте claim path AE3 и доступность automation-engine.',
                'details' => [
                    'intent_id' => $latest['id'] ?? null,
                    'intent_type' => $latest['intent_type'] ?? null,
                    'age_sec' => $ageSec,
                ],
            ]];
        }

        if ($status === 'running' && $ageSec >= $this->thresholds->int('scheduler_intent_running_warn_sec', 600)) {
            return [[
                'code' => 'scheduler_intent_running_stuck',
                'severity' => 'warning',
                'message' => 'Intent в running дольше ожидаемого',
                'recommendation' => 'Проверьте ae_tasks и lifecycle intent в Laravel.',
                'details' => [
                    'intent_id' => $latest['id'] ?? null,
                    'intent_type' => $latest['intent_type'] ?? null,
                    'age_sec' => $ageSec,
                ],
            ]];
        }

        return [];
    }

    /**
     * Intent в running при ae_task в pending после due_at — drift, если requeue завис.
     * Кратковременное расхождение после two-tank update_stage (due_at в будущем) — норма.
     *
     * @return list<array<string,mixed>>
     */
    private function intentDriftHangHints(int $zoneId): array
    {
        $driftAfterDueSec = $this->thresholds->int('scheduler_intent_task_drift_warn_sec', 45);

        $row = DB::selectOne(
            "SELECT zi.id AS intent_id,
                    zi.status AS intent_status,
                    zi.intent_type,
                    t.id AS task_id,
                    t.status AS task_status,
                    zi.idempotency_key
             FROM zone_automation_intents zi
             INNER JOIN ae_tasks t
               ON t.zone_id = zi.zone_id
              AND t.idempotency_key = zi.idempotency_key
              AND t.intent_id = zi.id
             WHERE zi.zone_id = ?
               AND zi.status = 'running'
               AND t.status = 'pending'
               AND (t.due_at IS NULL OR t.due_at <= NOW())
               AND EXTRACT(EPOCH FROM (NOW() - COALESCE(t.due_at, t.updated_at))) >= ?
             ORDER BY zi.updated_at DESC
             LIMIT 1",
            [$zoneId, $driftAfterDueSec],
        );

        if ($row === null) {
            return [];
        }

        return [[
            'code' => 'scheduler_intent_task_drift',
            'severity' => 'warning',
            'message' => 'Статус intent планировщика не совпадает со статусом ae_task',
            'recommendation' => 'Проверьте requeue two-tank, lifecycle intent в Laravel и worker AE3.',
            'details' => [
                'intent_id' => isset($row->intent_id) ? (int) $row->intent_id : null,
                'intent_status' => is_string($row->intent_status ?? null) ? $row->intent_status : null,
                'task_id' => isset($row->task_id) ? (int) $row->task_id : null,
                'task_status' => is_string($row->task_status ?? null) ? $row->task_status : null,
                'idempotency_key' => is_string($row->idempotency_key ?? null) ? $row->idempotency_key : null,
            ],
        ]];
    }

    /**
     * @param  array<string,mixed>  $observability
     * @return list<array<string,mixed>>
     */
    private function databaseHangHints(int $zoneId, array $observability): array
    {
        $hints = [];
        $runtime = is_array($observability['runtime'] ?? null) ? $observability['runtime'] : [];
        $nodes = is_array($observability['nodes'] ?? null) ? $observability['nodes'] : [];

        if (($nodes['offline_required'] ?? []) !== []) {
            $hints[] = [
                'code' => 'nodes_offline',
                'severity' => ($nodes['persistent_offline'] ?? false) ? 'critical' : 'warning',
                'message' => 'Обязательные узлы зоны offline или stale',
                'recommendation' => 'Проверьте питание, Wi‑Fi/MQTT и last_seen_at узлов irrig/ph/ec.',
                'details' => ['nodes' => $nodes['nodes'] ?? []],
            ];
        }

        $offlineNodes = collect($hints)->contains(fn (array $hint): bool => ($hint['code'] ?? '') === 'nodes_offline');

        if (! $offlineNodes && ($runtime['source'] ?? null) === 'laravel_db_fallback') {
            $workflowPhase = strtolower((string) ($runtime['workflow_phase'] ?? 'idle'));
            if (in_array($workflowPhase, ['tank_filling', 'tank_recirc', 'irrigating', 'irrig_recirc'], true)
                && ($runtime['task_is_active'] ?? false) !== true) {
                $hints[] = [
                    'code' => 'no_active_task_during_workflow',
                    'severity' => 'warning',
                    'message' => 'Активная фаза workflow без running-задачи AE3',
                    'recommendation' => 'Запустите start-cycle или проверьте pending intent планировщика.',
                    'details' => ['workflow_phase' => $workflowPhase, 'zone_id' => $zoneId],
                ];
            }
        }

        return $hints;
    }

    /**
     * @param  array<string,mixed>  $runtime
     * @return list<array<string,mixed>>
     */
    private function runtimeHangHints(array $runtime): array
    {
        if (($runtime['task_is_active'] ?? false) !== true) {
            return [];
        }

        $hints = [];
        $stageElapsed = (int) ($runtime['stage_elapsed_sec'] ?? 0);
        $waitingElapsed = (int) ($runtime['waiting_elapsed_sec'] ?? $stageElapsed);
        $status = strtolower((string) ($runtime['task_status'] ?? ''));

        if (($runtime['waiting_command'] ?? false) === true
            && $waitingElapsed >= $this->thresholds->int('waiting_command_warn_sec', 120)) {
            $hints[] = [
                'code' => 'waiting_command_stuck',
                'severity' => $waitingElapsed >= $this->thresholds->int('waiting_command_critical_sec', 300) ? 'critical' : 'warning',
                'message' => 'Задача ждёт ответа по команде дольше ожидаемого',
                'recommendation' => 'Проверьте MQTT, history-logger и command_response для последней команды.',
                'details' => [
                    'waiting_elapsed_sec' => $waitingElapsed,
                    'task_status' => $status,
                ],
            ];
        }

        $deadlineRemaining = $runtime['stage_deadline_remaining_sec'] ?? null;
        if (is_numeric($deadlineRemaining) && (int) $deadlineRemaining < 0) {
            $hints[] = [
                'code' => 'stage_deadline_exceeded',
                'severity' => 'critical',
                'message' => 'Превышен дедлайн текущего этапа',
                'recommendation' => 'Проверьте датчики уровня, узел irrig и последние команды fill/stop.',
                'details' => [
                    'overdue_sec' => abs((int) $deadlineRemaining),
                    'current_stage' => $runtime['current_stage'] ?? null,
                ],
            ];
        }

        $currentStage = strtolower((string) ($runtime['current_stage'] ?? ''));
        $stageThresholds = $this->thresholds->stageElapsed($currentStage);
        $deadlineRemaining = $runtime['stage_deadline_remaining_sec'] ?? null;
        $skipElapsedLong = $this->shouldSkipStageElapsedLongForActiveDeadline($currentStage, $deadlineRemaining);
        if ($stageThresholds !== null && $stageElapsed >= $stageThresholds['warn'] && ! $skipElapsedLong) {
            $hints[] = [
                'code' => 'stage_elapsed_long',
                'severity' => $stageElapsed >= $stageThresholds['critical'] ? 'critical' : 'warning',
                'message' => "Этап выполняется дольше типового времени: {$currentStage}",
                'recommendation' => 'Сверьте уровни баков, online-статус irrig-ноды и журнал zone_events.',
                'details' => [
                    'stage_elapsed_sec' => $stageElapsed,
                    'current_stage' => $currentStage,
                ],
            ];
        }

        return $hints;
    }

    private function shouldSkipStageElapsedLongForActiveDeadline(string $stage, mixed $deadlineRemainingSec): bool
    {
        $normalized = strtolower(trim($stage));
        if (! in_array($normalized, ['irrigation_check', 'irrigation_recovery_check'], true)) {
            return false;
        }
        if (! is_numeric($deadlineRemainingSec)) {
            return false;
        }

        return (int) $deadlineRemainingSec > 0;
    }

    /**
     * @param  list<array<string,mixed>>  $hints
     * @return list<array<string,mixed>>
     */
    private function dedupeHangHints(array $hints): array
    {
        $seen = [];
        $result = [];

        usort($hints, function (array $left, array $right): int {
            $rank = ['critical' => 2, 'warning' => 1, 'info' => 0];

            return ($rank[$right['severity'] ?? 'info'] ?? 0) <=> ($rank[$left['severity'] ?? 'info'] ?? 0);
        });

        foreach ($hints as $hint) {
            $code = (string) ($hint['code'] ?? '');
            if ($code === '' || isset($seen[$code])) {
                continue;
            }
            $seen[$code] = true;
            $result[] = $hint;
        }

        return $result;
    }

    /**
     * @param  list<array<string,mixed>>  $hints
     * @param  array<string,mixed>  $runtime
     */
    private function resolveOverallHealth(array $hints, array $runtime): string
    {
        foreach ($hints as $hint) {
            if (($hint['severity'] ?? '') === 'critical') {
                return 'critical';
            }
        }

        foreach ($hints as $hint) {
            if (($hint['severity'] ?? '') === 'warning') {
                return 'warning';
            }
        }

        if (($runtime['task_is_active'] ?? false) === true) {
            return 'active';
        }

        return 'idle';
    }

    /**
     * @return array<string,mixed>
     */
    private function buildCorrectionContext(int $zoneId, ?int $activeTaskId = null): array
    {
        return [
            'last_dose' => $this->fetchPidStateLastDoses($zoneId),
            'latest_skip' => $this->fetchLatestCorrectionSkipEvent($zoneId, $activeTaskId),
            'readiness' => $this->fetchLatestCorrectionReadiness($zoneId, $activeTaskId),
            'prepare_baseline' => $this->fetchLatestPrepareBaseline($zoneId),
            'pipeline' => $this->fetchCorrectionPipelineState($zoneId, $activeTaskId),
        ];
    }

    /**
     * @return array<string,mixed>|null
     */
    private function fetchLatestPrepareBaseline(int $zoneId): ?array
    {
        if (! DB::getSchemaBuilder()->hasTable('zone_prepare_baselines')) {
            return null;
        }

        $row = DB::table('zone_prepare_baselines')
            ->where('zone_id', $zoneId)
            ->orderByDesc('captured_at')
            ->orderByDesc('id')
            ->first();

        if ($row === null) {
            return null;
        }

        $ratios = $this->decodeJsonColumn($row->ratios_json ?? null);
        $targets = $this->decodeJsonColumn($row->component_targets_json ?? null);

        return [
            'id' => isset($row->id) ? (int) $row->id : null,
            'grow_cycle_id' => isset($row->grow_cycle_id) ? (int) $row->grow_cycle_id : null,
            'ae_task_id' => isset($row->ae_task_id) ? (int) $row->ae_task_id : null,
            'water_ec' => isset($row->water_ec) ? (float) $row->water_ec : null,
            'water_ph' => isset($row->water_ph) ? (float) $row->water_ph : null,
            'target_ec' => isset($row->target_ec) ? (float) $row->target_ec : null,
            'nutrient_ec_budget' => isset($row->nutrient_ec_budget) ? (float) $row->nutrient_ec_budget : null,
            'ratios' => $ratios,
            'component_targets' => $targets,
            'captured_at' => isset($row->captured_at)
                ? Carbon::parse((string) $row->captured_at)->toIso8601String()
                : null,
            'source' => is_string($row->source ?? null) ? (string) $row->source : null,
        ];
    }

    /**
     * @return array<string,mixed>|null
     */
    private function fetchCorrectionPipelineState(int $zoneId, ?int $activeTaskId = null): ?array
    {
        if (! DB::getSchemaBuilder()->hasTable('ae_tasks')) {
            return null;
        }

        $schema = DB::getSchemaBuilder();
        $columns = array_values(array_filter([
            'id',
            $schema->hasColumn('ae_tasks', 'corr_pipeline_phase') ? 'corr_pipeline_phase' : null,
            $schema->hasColumn('ae_tasks', 'corr_active_component') ? 'corr_active_component' : null,
            $schema->hasColumn('ae_tasks', 'corr_water_ec') ? 'corr_water_ec' : null,
            $schema->hasColumn('ae_tasks', 'corr_water_ph') ? 'corr_water_ph' : null,
            $schema->hasColumn('ae_tasks', 'corr_nutrient_budget') ? 'corr_nutrient_budget' : null,
            $schema->hasColumn('ae_tasks', 'corr_component_targets_json') ? 'corr_component_targets_json' : null,
            $schema->hasColumn('ae_tasks', 'corr_dilute_attempts') ? 'corr_dilute_attempts' : null,
            $schema->hasColumn('ae_tasks', 'corr_ec_pid_frozen') ? 'corr_ec_pid_frozen' : null,
            $schema->hasColumn('ae_tasks', 'corr_baseline_id') ? 'corr_baseline_id' : null,
        ]));

        if (count($columns) <= 1) {
            return null;
        }

        $query = DB::table('ae_tasks')->where('zone_id', $zoneId);
        if ($activeTaskId !== null) {
            $query->where('id', $activeTaskId);
        } else {
            $placeholders = implode(',', array_fill(0, count(self::ACTIVE_TASK_STATUSES), '?'));
            $query->whereRaw("status IN ({$placeholders})", self::ACTIVE_TASK_STATUSES)
                ->orderByDesc('updated_at')
                ->orderByDesc('id');
        }

        $row = $query->first($columns);

        if ($row === null) {
            return null;
        }

        $hasPipeline = ($row->corr_pipeline_phase ?? null) !== null
            || ($row->corr_active_component ?? null) !== null
            || ($row->corr_water_ec ?? null) !== null
            || ($row->corr_component_targets_json ?? null) !== null;

        if (! $hasPipeline) {
            return null;
        }

        $targets = $this->decodeJsonColumn($row->corr_component_targets_json ?? null);

        return [
            'task_id' => isset($row->id) ? (int) $row->id : null,
            'pipeline_phase' => is_string($row->corr_pipeline_phase ?? null) ? (string) $row->corr_pipeline_phase : null,
            'active_component' => is_string($row->corr_active_component ?? null) ? (string) $row->corr_active_component : null,
            'water_ec' => isset($row->corr_water_ec) ? (float) $row->corr_water_ec : null,
            'water_ph' => isset($row->corr_water_ph) ? (float) $row->corr_water_ph : null,
            'nutrient_budget' => isset($row->corr_nutrient_budget) ? (float) $row->corr_nutrient_budget : null,
            'component_targets' => $targets,
            'dilute_attempts' => isset($row->corr_dilute_attempts) ? (int) $row->corr_dilute_attempts : null,
            'ec_pid_frozen' => isset($row->corr_ec_pid_frozen) ? (bool) $row->corr_ec_pid_frozen : null,
            'baseline_id' => isset($row->corr_baseline_id) ? (int) $row->corr_baseline_id : null,
        ];
    }

    /**
     * @return array<string,mixed>|null
     */
    private function decodeJsonColumn(mixed $raw): ?array
    {
        if (is_array($raw)) {
            return array_is_list($raw) ? null : $raw;
        }

        if (! is_string($raw) || trim($raw) === '') {
            return null;
        }

        try {
            $decoded = json_decode($raw, true, 512, JSON_THROW_ON_ERROR);
        } catch (\Throwable) {
            return null;
        }

        return is_array($decoded) && ! array_is_list($decoded) ? $decoded : null;
    }

    /**
     * @return array<string,array<string,mixed>>
     */
    private function fetchPidStateLastDoses(int $zoneId): array
    {
        if (! DB::getSchemaBuilder()->hasTable('pid_state')) {
            return [];
        }

        $rows = DB::table('pid_state')
            ->where('zone_id', $zoneId)
            ->whereIn('pid_type', ['ec', 'ph'])
            ->get(['pid_type', 'last_dose_at', 'no_effect_count']);

        $result = [];
        $now = Carbon::now();

        foreach ($rows as $row) {
            $pidType = strtolower((string) ($row->pid_type ?? ''));
            if (! in_array($pidType, ['ec', 'ph'], true)) {
                continue;
            }

            $lastDoseAt = $row->last_dose_at ?? null;
            $ageSec = null;
            if ($lastDoseAt !== null) {
                $ageSec = max(0, Carbon::parse((string) $lastDoseAt)->diffInSeconds($now));
            }

            $result[$pidType] = [
                'last_dose_at' => $lastDoseAt !== null
                    ? Carbon::parse((string) $lastDoseAt)->toIso8601String()
                    : null,
                'last_dose_age_sec' => $ageSec,
                'no_effect_count' => isset($row->no_effect_count) ? (int) $row->no_effect_count : 0,
            ];
        }

        return $result;
    }

    /**
     * @return array<string,mixed>|null
     */
    private function fetchLatestCorrectionSkipEvent(int $zoneId, ?int $activeTaskId = null): ?array
    {
        if (! DB::getSchemaBuilder()->hasTable('zone_events')) {
            return null;
        }

        $placeholders = implode(',', array_fill(0, count(self::CORRECTION_SKIP_EVENT_TYPES), '?'));
        $minCreatedAt = Carbon::now()->subSeconds(self::CORRECTION_EVENT_MAX_AGE_SEC);

        $bindings = array_merge([$zoneId], self::CORRECTION_SKIP_EVENT_TYPES, [$minCreatedAt]);
        $taskFilter = '';
        if ($activeTaskId !== null) {
            // Prefer events of the active task; allow legacy rows without task_id.
            $taskFilter = " AND (
                (payload_json->>'task_id')::bigint = ?
                OR payload_json->>'task_id' IS NULL
            )";
            $bindings[] = $activeTaskId;
        }

        $row = DB::selectOne(
            "SELECT id, type, payload_json, created_at
             FROM zone_events
             WHERE zone_id = ?
               AND type IN ({$placeholders})
               AND created_at >= ?
               {$taskFilter}
             ORDER BY
               CASE
                 WHEN payload_json->>'task_id' IS NOT NULL THEN 0
                 ELSE 1
               END,
               id DESC
             LIMIT 1",
            $bindings,
        );

        if ($row === null) {
            return null;
        }

        $payload = $this->decodeZoneEventPayload($row->payload_json ?? null);
        $createdAt = $row->created_at ?? null;
        $ageSec = $createdAt !== null
            ? max(0, Carbon::parse((string) $createdAt)->diffInSeconds(now()))
            : null;

        $summary = $this->summarizeCorrectionSkipPayload($payload);
        if (isset($payload['task_id'])) {
            $summary['task_id'] = (int) $payload['task_id'];
        }

        return [
            'event_id' => isset($row->id) ? (int) $row->id : null,
            'event_type' => is_string($row->type ?? null) ? (string) $row->type : null,
            'occurred_at' => $createdAt !== null
                ? Carbon::parse((string) $createdAt)->toIso8601String()
                : null,
            'age_sec' => $ageSec,
            'payload' => $summary,
        ];
    }

    /**
     * @return array<string,mixed>|null
     */
    private function fetchLatestCorrectionReadiness(int $zoneId, ?int $activeTaskId = null): ?array
    {
        if (! DB::getSchemaBuilder()->hasTable('zone_events')) {
            return null;
        }

        $placeholders = implode(',', array_fill(0, count(self::CORRECTION_READINESS_EVENT_TYPES), '?'));
        $minCreatedAt = Carbon::now()->subSeconds(self::CORRECTION_EVENT_MAX_AGE_SEC);

        $bindings = array_merge([$zoneId], self::CORRECTION_READINESS_EVENT_TYPES, [$minCreatedAt]);
        $taskFilter = '';
        if ($activeTaskId !== null) {
            $taskFilter = " AND (
                (payload_json->>'task_id')::bigint = ?
                OR payload_json->>'task_id' IS NULL
            )";
            $bindings[] = $activeTaskId;
        }

        $row = DB::selectOne(
            "SELECT id, type, payload_json, created_at
             FROM zone_events
             WHERE zone_id = ?
               AND type IN ({$placeholders})
               AND created_at >= ?
               {$taskFilter}
             ORDER BY
               CASE
                 WHEN payload_json->>'task_id' IS NOT NULL THEN 0
                 ELSE 1
               END,
               id DESC
             LIMIT 1",
            $bindings,
        );

        if ($row === null) {
            return null;
        }

        $payload = $this->decodeZoneEventPayload($row->payload_json ?? null);

        return [
            'event_id' => isset($row->id) ? (int) $row->id : null,
            'event_type' => is_string($row->type ?? null) ? (string) $row->type : null,
            'occurred_at' => ($row->created_at ?? null) !== null
                ? Carbon::parse((string) $row->created_at)->toIso8601String()
                : null,
            'targets_in_tolerance' => array_key_exists('targets_in_tolerance', $payload)
                ? (bool) $payload['targets_in_tolerance']
                : null,
            'workflow_ready' => array_key_exists('workflow_ready', $payload)
                ? (bool) $payload['workflow_ready']
                : null,
        ];
    }

    /**
     * @return array<string,mixed>
     */
    private function decodeZoneEventPayload(mixed $raw): array
    {
        if (is_array($raw)) {
            return $raw;
        }

        if (! is_string($raw) || trim($raw) === '') {
            return [];
        }

        $decoded = json_decode($raw, true);

        return is_array($decoded) ? $decoded : [];
    }

    /**
     * @param  array<string,mixed>  $payload
     * @return array<string,mixed>
     */
    private function summarizeCorrectionSkipPayload(array $payload): array
    {
        $keys = [
            'reason',
            'retry_after_sec',
            'sensor_scope',
            'sensor_type',
            'deferred_action',
            'selected_action',
            'control_mode',
            'failed_component',
            'status',
            'mode',
            'error_code',
            'ph_reason',
            'ec_reason',
            'estop_event_id',
            'pid_type',
            'alert_block_retry',
            'alert_block_max_retries',
            'retry_count',
            'task_id',
        ];

        $summary = [];
        foreach ($keys as $key) {
            if (! array_key_exists($key, $payload)) {
                continue;
            }
            $summary[$key] = $payload[$key];
        }

        return $summary;
    }
}
