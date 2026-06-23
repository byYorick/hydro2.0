<?php

namespace App\Services;

use Illuminate\Support\Carbon;
use Illuminate\Support\Facades\DB;

class ZoneAutomationObservabilityService
{
    private const ACTIVE_TASK_STATUSES = ['pending', 'claimed', 'running', 'waiting_command'];

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

        $payload['observability'] = $observability;

        return $payload;
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
            $stageDeadlineRemainingSec = Carbon::parse((string) $task->stage_deadline_at)->diffInSeconds(now(), false);
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
        if ($stageThresholds !== null && $stageElapsed >= $stageThresholds['warn']) {
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
}
