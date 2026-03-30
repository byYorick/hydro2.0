<?php

namespace App\Services\AutomationScheduler;

use Carbon\CarbonImmutable;
use Illuminate\Support\Collection;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Schema;

class ExecutionRunReadModel
{
    public function __construct(
        private readonly ExecutionTimelineReader $timelineReader,
        private readonly \App\Services\ErrorCodeCatalogService $errorCodeCatalog,
    ) {}

    /**
     * @return array<int, array<string, mixed>>
     */
    public function listForZone(int $zoneId, int $limit = 10): array
    {
        if (! Schema::hasTable('ae_tasks')) {
            return [];
        }

        $safeLimit = max(1, min($limit, 50));
        $rows = $this->baseQuery($zoneId)
            ->orderByDesc('tasks.updated_at')
            ->orderByDesc('tasks.id')
            ->limit($safeLimit)
            ->get();

        return $this->mapRows($rows);
    }

    /**
     * @return array<string, mixed>|null
     */
    public function findForZone(int $zoneId, string $executionId): ?array
    {
        if (! Schema::hasTable('ae_tasks')) {
            return null;
        }

        $normalizedExecutionId = trim($executionId);
        if ($normalizedExecutionId === '' || preg_match('/^\d+$/', $normalizedExecutionId) !== 1) {
            return null;
        }

        $row = $this->baseQuery($zoneId)
            ->where('tasks.id', (int) $normalizedExecutionId)
            ->first();

        if ($row === null) {
            return null;
        }

        $mapped = $this->mapRows(collect([$row]))[0] ?? null;
        if ($mapped === null) {
            return null;
        }

        $mapped['timeline'] = $this->timelineReader->readForExecution(
            $zoneId,
            (string) $mapped['execution_id'],
            is_string($mapped['correlation_id'] ?? null) ? $mapped['correlation_id'] : null,
        );

        $mapped['timeline_preview'] = array_slice($mapped['timeline'], 0, 5);
        $mapped['latest_event'] = $mapped['timeline'] !== [] ? $mapped['timeline'][count($mapped['timeline']) - 1] : null;

        return $mapped;
    }

    /**
     * @return array<string, mixed>
     */
    public function countersForZone(int $zoneId): array
    {
        if (! Schema::hasTable('ae_tasks') && ! Schema::hasTable('zone_automation_intents')) {
            return [
                'active' => 0,
                'completed_24h' => 0,
                'failed_24h' => 0,
            ];
        }

        $since = now()->subDay();

        $active = Schema::hasTable('ae_tasks')
            ? DB::table('ae_tasks')
                ->where('zone_id', $zoneId)
                ->whereIn('status', ['pending', 'claimed', 'running', 'waiting_command'])
                ->count()
            : 0;

        $completedTasks = Schema::hasTable('ae_tasks')
            ? DB::table('ae_tasks')
                ->where('zone_id', $zoneId)
                ->where('status', 'completed')
                ->where('updated_at', '>=', $since)
                ->count()
            : 0;

        $failedTasks = Schema::hasTable('ae_tasks')
            ? DB::table('ae_tasks')
                ->where('zone_id', $zoneId)
                ->whereIn('status', ['failed', 'cancelled'])
                ->where('updated_at', '>=', $since)
                ->count()
            : 0;

        $completedIntentOnly = 0;
        $failedIntentOnly = 0;
        if (Schema::hasTable('zone_automation_intents')) {
            $intentOnlyBaseQuery = DB::table('zone_automation_intents as intents')
                ->leftJoin('ae_tasks as tasks', function ($join): void {
                    $join
                        ->on('tasks.intent_id', '=', 'intents.id')
                        ->on('tasks.zone_id', '=', 'intents.zone_id');
                })
                ->where('intents.zone_id', $zoneId)
                ->whereNull('tasks.id')
                ->where('intents.updated_at', '>=', $since);

            $completedIntentOnly = (clone $intentOnlyBaseQuery)
                ->where('intents.status', 'completed')
                ->count();

            $failedIntentOnly = (clone $intentOnlyBaseQuery)
                ->whereIn('intents.status', ['failed', 'cancelled'])
                ->count();
        }

        return [
            'active' => (int) $active,
            'completed_24h' => (int) ($completedTasks + $completedIntentOnly),
            'failed_24h' => (int) ($failedTasks + $failedIntentOnly),
        ];
    }

    /**
     * @return array<string, mixed>|null
     */
    public function latestFailureForZone(int $zoneId): ?array
    {
        $latestTaskFailure = $this->latestFailedTaskForZone($zoneId);
        $latestIntentFailure = $this->latestFailedIntentWithoutTaskForZone($zoneId);

        if ($latestTaskFailure === null) {
            return $latestIntentFailure;
        }

        if ($latestIntentFailure === null) {
            return $latestTaskFailure;
        }

        $taskFailureAt = $this->toIso8601($latestTaskFailure['at'] ?? null);
        $intentFailureAt = $this->toIso8601($latestIntentFailure['at'] ?? null);

        if ($taskFailureAt === null) {
            return $latestIntentFailure;
        }

        if ($intentFailureAt === null) {
            return $latestTaskFailure;
        }

        return strcmp($taskFailureAt, $intentFailureAt) >= 0
            ? $latestTaskFailure
            : $latestIntentFailure;
    }

    private function baseQuery(int $zoneId)
    {
        $select = [
            'tasks.id',
            'tasks.zone_id',
            'tasks.status as runtime_status',
            'tasks.task_type as runtime_task_type',
            'tasks.idempotency_key as runtime_idempotency_key',
            'tasks.current_stage',
            'tasks.workflow_phase',
            'tasks.error_code',
            'tasks.error_message',
            'tasks.scheduled_for',
            'tasks.due_at',
            'tasks.claimed_at',
            'tasks.completed_at',
            'tasks.stage_entered_at',
            'tasks.control_mode_snapshot',
            'tasks.created_at',
            'tasks.updated_at',
            'tasks.intent_id',
            'intents.intent_type',
            'intents.status as intent_status',
            'intents.idempotency_key as correlation_id',
            'intents.payload as intent_payload',
        ];

        $select[] = $this->optionalTaskColumnSelect('irrigation_mode');
        $select[] = $this->optionalTaskColumnSelect('irrigation_requested_duration_sec');
        $select[] = $this->optionalTaskColumnSelect('irrigation_decision_strategy');
        $select[] = $this->optionalTaskColumnSelect('irrigation_decision_outcome');
        $select[] = $this->optionalTaskColumnSelect('irrigation_decision_reason_code');
        $select[] = $this->optionalTaskColumnSelect('irrigation_decision_degraded');
        $select[] = $this->optionalTaskColumnSelect('irrigation_replay_count');

        return DB::table('ae_tasks as tasks')
            ->leftJoin('zone_automation_intents as intents', function ($join): void {
                $join
                    ->on('intents.id', '=', 'tasks.intent_id')
                    ->on('intents.zone_id', '=', 'tasks.zone_id');
            })
            ->where('tasks.zone_id', $zoneId)
            ->select($select);
    }

    private function optionalTaskColumnSelect(string $column): string|\Illuminate\Database\Query\Expression
    {
        if (Schema::hasColumn('ae_tasks', $column)) {
            return "tasks.{$column}";
        }

        return DB::raw("NULL as {$column}");
    }

    /**
     * @param  Collection<int, object>  $rows
     * @return array<int, array<string, mixed>>
     */
    private function mapRows(Collection $rows): array
    {
        $executionIds = $rows
            ->map(static fn ($row): string => (string) ($row->id ?? ''))
            ->filter(static fn (string $value): bool => $value !== '')
            ->values()
            ->all();

        $activeTaskRows = [];
        if ($executionIds !== [] && Schema::hasTable('laravel_scheduler_active_tasks')) {
            $activeTaskRows = DB::table('laravel_scheduler_active_tasks')
                ->whereIn('task_id', $executionIds)
                ->get()
                ->keyBy(static fn ($row): string => (string) ($row->task_id ?? ''))
                ->all();
        }

        return $rows->map(function ($row) use ($activeTaskRows): array {
            $executionId = (string) ($row->id ?? '');
            $activeTask = $activeTaskRows[$executionId] ?? null;
            $intentPayload = $this->normalizeJson($row->intent_payload ?? null);

            $taskType = $this->resolvePublicTaskType(
                activeTaskType: is_object($activeTask) ? (string) ($activeTask->task_type ?? '') : '',
                intentPayload: $intentPayload,
                intentType: (string) ($row->intent_type ?? ''),
                runtimeTaskType: (string) ($row->runtime_task_type ?? ''),
            );
            $status = $this->normalizeExecutionStatus((string) ($row->runtime_status ?? ''));
            $correlationId = trim((string) ($row->correlation_id ?? $row->runtime_idempotency_key ?? ''));
            $summary = [
                'execution_id' => $executionId,
                'task_id' => $executionId,
                'zone_id' => (int) ($row->zone_id ?? 0),
                'task_type' => $taskType,
                'schedule_task_type' => is_object($activeTask) ? $this->resolveString($activeTask->task_type ?? null) : null,
                'status' => $status,
                'runtime_status' => $this->resolveString($row->runtime_status ?? null),
                'intent_status' => $this->resolveString($row->intent_status ?? null),
                'intent_type' => $this->resolveString($row->intent_type ?? null),
                'correlation_id' => $correlationId !== '' ? $correlationId : null,
                'schedule_key' => is_object($activeTask) ? $this->resolveString($activeTask->schedule_key ?? null) : null,
                'control_mode_snapshot' => $this->resolveString($row->control_mode_snapshot ?? null),
                'current_stage' => $this->resolveString($row->current_stage ?? null),
                'workflow_phase' => $this->resolveString($row->workflow_phase ?? null),
                'irrigation_mode' => $this->resolveString($row->irrigation_mode ?? null),
                'requested_duration_sec' => isset($row->irrigation_requested_duration_sec) && is_numeric($row->irrigation_requested_duration_sec)
                    ? (int) $row->irrigation_requested_duration_sec
                    : null,
                'decision_strategy' => $this->resolveString($row->irrigation_decision_strategy ?? null),
                'decision_outcome' => $this->resolveString($row->irrigation_decision_outcome ?? null),
                'decision_reason_code' => $this->resolveString($row->irrigation_decision_reason_code ?? null),
                'decision_degraded' => $this->normalizeOptionalBool($row->irrigation_decision_degraded ?? null),
                'replay_count' => isset($row->irrigation_replay_count) && is_numeric($row->irrigation_replay_count)
                    ? (int) $row->irrigation_replay_count
                    : 0,
                'created_at' => $this->toIso8601($row->created_at ?? null),
                'updated_at' => $this->toIso8601($row->updated_at ?? null),
                'scheduled_for' => $this->toIso8601($row->scheduled_for ?? null),
                'accepted_at' => is_object($activeTask) ? $this->toIso8601($activeTask->accepted_at ?? null) : null,
                'due_at' => is_object($activeTask) ? $this->toIso8601($activeTask->due_at ?? null) : $this->toIso8601($row->due_at ?? null),
                'expires_at' => is_object($activeTask) ? $this->toIso8601($activeTask->expires_at ?? null) : null,
                'completed_at' => $this->toIso8601($row->completed_at ?? null),
                'error_code' => $this->resolveString($row->error_code ?? null),
                'error_message' => $this->resolveString($row->error_message ?? null),
                'human_error_message' => $this->errorCodeCatalog->present(
                    $this->resolveString($row->error_code ?? null),
                    $this->resolveString($row->error_message ?? null),
                )['message'],
                'is_active' => in_array((string) ($row->runtime_status ?? ''), ['pending', 'claimed', 'running', 'waiting_command'], true),
            ];

            $summary['lifecycle'] = $this->buildLifecycle($summary, $row);

            return $summary;
        })->values()->all();
    }

    /**
     * @param  array<string, mixed>  $summary
     * @return array<int, array<string, mixed>>
     */
    private function buildLifecycle(array $summary, object $row): array
    {
        $lifecycle = [];

        $acceptedAt = $summary['accepted_at'] ?? $summary['created_at'] ?? null;
        if (is_string($acceptedAt) && $acceptedAt !== '') {
            $lifecycle[] = [
                'status' => 'accepted',
                'at' => $acceptedAt,
                'source' => 'ae_tasks',
            ];
        }

        $runningAt = $this->toIso8601($row->claimed_at ?? null)
            ?? $this->toIso8601($row->stage_entered_at ?? null);
        if (in_array((string) ($row->runtime_status ?? ''), ['running', 'waiting_command'], true) && $runningAt !== null) {
            $lifecycle[] = [
                'status' => 'running',
                'at' => $runningAt,
                'source' => 'ae_tasks',
            ];
        }

        if (in_array((string) ($summary['status'] ?? ''), ['completed', 'failed', 'cancelled'], true)) {
            $lifecycle[] = [
                'status' => (string) $summary['status'],
                'at' => $summary['completed_at'] ?? $summary['updated_at'] ?? null,
                'error' => $summary['human_error_message'] ?? $summary['error_message'] ?? null,
                'source' => 'ae_tasks',
            ];
        }

        return $lifecycle;
    }

    /**
     * @return array<string, mixed>|null
     */
    private function latestFailedTaskForZone(int $zoneId): ?array
    {
        if (! Schema::hasTable('ae_tasks')) {
            return null;
        }

        $row = DB::table('ae_tasks as tasks')
            ->leftJoin('zone_automation_intents as intents', function ($join): void {
                $join
                    ->on('intents.id', '=', 'tasks.intent_id')
                    ->on('intents.zone_id', '=', 'tasks.zone_id');
            })
            ->where('tasks.zone_id', $zoneId)
            ->whereIn('tasks.status', ['failed', 'cancelled'])
            ->orderByDesc('tasks.updated_at')
            ->orderByDesc('tasks.id')
            ->first([
                'tasks.id',
                'tasks.zone_id',
                'tasks.status',
                'tasks.task_type as runtime_task_type',
                'tasks.error_code',
                'tasks.error_message',
                'tasks.updated_at',
                'tasks.intent_id',
                'intents.intent_type',
                'intents.payload as intent_payload',
            ]);

        if (! is_object($row)) {
            return null;
        }

        $intentPayload = $this->normalizeJson($row->intent_payload ?? null);

        $errorCode = $this->resolveString($row->error_code ?? null);
        $errorMessage = $this->resolveString($row->error_message ?? null);

        return [
            'source' => 'ae_tasks',
            'task_id' => (string) ($row->id ?? ''),
            'intent_id' => isset($row->intent_id) ? (string) $row->intent_id : null,
            'task_type' => $this->resolvePublicTaskType(
                activeTaskType: '',
                intentPayload: $intentPayload,
                intentType: (string) ($row->intent_type ?? ''),
                runtimeTaskType: (string) ($row->runtime_task_type ?? ''),
            ),
            'status' => $this->normalizeExecutionStatus((string) ($row->status ?? '')),
            'error_code' => $errorCode,
            'error_message' => $errorMessage,
            'human_error_message' => $this->errorCodeCatalog->present($errorCode, $errorMessage)['message'],
            'at' => $this->toIso8601($row->updated_at ?? null),
        ];
    }

    /**
     * @return array<string, mixed>|null
     */
    private function latestFailedIntentWithoutTaskForZone(int $zoneId): ?array
    {
        if (! Schema::hasTable('zone_automation_intents')) {
            return null;
        }

        $row = DB::table('zone_automation_intents as intents')
            ->leftJoin('ae_tasks as tasks', function ($join): void {
                $join
                    ->on('tasks.intent_id', '=', 'intents.id')
                    ->on('tasks.zone_id', '=', 'intents.zone_id');
            })
            ->where('intents.zone_id', $zoneId)
            ->whereNull('tasks.id')
            ->whereIn('intents.status', ['failed', 'cancelled'])
            ->orderByDesc('intents.updated_at')
            ->orderByDesc('intents.id')
            ->first([
                'intents.id',
                'intents.intent_type',
                'intents.status',
                'intents.payload',
                'intents.error_code',
                'intents.error_message',
                'intents.updated_at',
            ]);

        if (! is_object($row)) {
            return null;
        }

        $intentPayload = $this->normalizeJson($row->payload ?? null);

        $errorCode = $this->resolveString($row->error_code ?? null);
        $errorMessage = $this->resolveString($row->error_message ?? null);

        return [
            'source' => 'zone_automation_intents',
            'task_id' => null,
            'intent_id' => (string) ($row->id ?? ''),
            'task_type' => $this->resolvePublicTaskType(
                activeTaskType: '',
                intentPayload: $intentPayload,
                intentType: (string) ($row->intent_type ?? ''),
                runtimeTaskType: '',
            ),
            'status' => $this->normalizeExecutionStatus((string) ($row->status ?? '')),
            'error_code' => $errorCode,
            'error_message' => $errorMessage,
            'human_error_message' => $this->errorCodeCatalog->present($errorCode, $errorMessage)['message'],
            'at' => $this->toIso8601($row->updated_at ?? null),
        ];
    }

    /**
     * @param  array<string, mixed>  $intentPayload
     */
    private function resolvePublicTaskType(
        string $activeTaskType,
        array $intentPayload,
        string $intentType,
        string $runtimeTaskType,
    ): string {
        $candidates = [
            strtolower(trim($activeTaskType)),
            strtolower(trim((string) ($intentPayload['task_type'] ?? ''))),
            strtolower(trim($intentType)),
            strtolower(trim($runtimeTaskType)),
        ];

        foreach ($candidates as $candidate) {
            if ($candidate === '') {
                continue;
            }

            return match ($candidate) {
                'ventilation' => 'climate',
                'lighting_tick', 'lighting' => 'lighting',
                'irrigate_once', 'irrigation', 'irrigation_start', 'cycle_start' => 'irrigation',
                default => $candidate,
            };
        }

        return 'irrigation';
    }

    private function normalizeExecutionStatus(string $runtimeStatus): string
    {
        $normalized = strtolower(trim($runtimeStatus));

        return match ($normalized) {
            'pending', 'claimed' => 'accepted',
            'running', 'waiting_command' => 'running',
            'completed' => 'completed',
            'failed', 'timeout', 'error' => 'failed',
            'cancelled' => 'cancelled',
            default => $normalized !== '' ? $normalized : 'unknown',
        };
    }

    /**
     * @return array<string, mixed>
     */
    private function normalizeJson(mixed $value): array
    {
        if (is_array($value)) {
            return $value;
        }

        if (is_string($value) && trim($value) !== '') {
            $decoded = json_decode($value, true);
            if (is_array($decoded)) {
                return $decoded;
            }
        }

        return [];
    }

    private function normalizeOptionalBool(mixed $value): ?bool
    {
        if (is_bool($value)) {
            return $value;
        }
        if (is_int($value) || is_float($value)) {
            return (bool) $value;
        }
        if (is_string($value)) {
            $normalized = strtolower(trim($value));
            if (in_array($normalized, ['1', 'true', 'yes', 'on'], true)) {
                return true;
            }
            if (in_array($normalized, ['0', 'false', 'no', 'off'], true)) {
                return false;
            }
        }

        return null;
    }

    private function resolveString(mixed $value): ?string
    {
        if (! is_string($value)) {
            return null;
        }

        $normalized = trim($value);

        return $normalized !== '' ? $normalized : null;
    }

    private function toIso8601(mixed $value): ?string
    {
        if ($value === null || $value === '') {
            return null;
        }

        try {
            return CarbonImmutable::parse((string) $value)->utc()->toIso8601String();
        } catch (\Throwable) {
            return null;
        }
    }
}
