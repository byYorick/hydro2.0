<?php

namespace App\Services\AutomationScheduler;

use App\Models\LaravelSchedulerActiveTask;
use App\Models\SchedulerLog;
use Carbon\CarbonImmutable;
use Illuminate\Support\Facades\Cache;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Log;

class ActiveTaskPoller
{
    use ResolvesAutomationRuntime;

    public function __construct(
        private readonly ActiveTaskStore $activeTaskStore,
    ) {}

    /**
     * @param  array<string, mixed>  $cfg
     * @param  callable(string, string, array<string, mixed>): void  $writeLog
     * @return array<string, bool>
     */
    public function reconcilePendingActiveTasks(array $cfg, callable $writeLog): array
    {
        $pollLimit = max(1, (int) ($cfg['active_task_poll_batch'] ?? 500));
        $pendingTasks = $this->activeTaskStore->listPendingForPolling($pollLimit);
        if ($pendingTasks->isEmpty()) {
            return [];
        }

        $now = SchedulerRuntimeHelper::nowUtc();
        $prefetchedStatuses = $this->prefetchAe3IntentStatuses($pendingTasks);
        /** @var array<string, bool> $busyness */
        $busyness = [];

        foreach ($pendingTasks as $task) {
            if (! $task instanceof LaravelSchedulerActiveTask) {
                continue;
            }

            $taskId = trim((string) $task->task_id);
            if ($taskId === '') {
                continue;
            }

            $scheduleKey = trim((string) $task->schedule_key);
            $isBusy = $this->reconcilePersistedActiveTask(
                task: $task,
                cfg: $cfg,
                now: $now,
                writeLog: $writeLog,
                prefetchedStatuses: $prefetchedStatuses,
            );

            if ($scheduleKey === '') {
                continue;
            }

            $busyness[$scheduleKey] = $isBusy;

            $cacheKey = SchedulerRuntimeHelper::activeTaskCacheKey($scheduleKey);
            if ($isBusy) {
                Cache::put($cacheKey, ['task_id' => $taskId], now()->addSeconds($cfg['active_task_ttl_sec']));

                continue;
            }

            Cache::forget($cacheKey);
        }

        return $busyness;
    }

    /**
     * @param  array<string, mixed>  $cfg
     * @param  array<string, bool>  $reconciledBusyness
     * @param  callable(string, string, array<string, mixed>): void  $writeLog
     */
    public function isScheduleBusy(
        string $scheduleKey,
        array $cfg,
        array $reconciledBusyness,
        callable $writeLog,
    ): bool {
        if (array_key_exists($scheduleKey, $reconciledBusyness)) {
            return $reconciledBusyness[$scheduleKey];
        }

        $cacheKey = SchedulerRuntimeHelper::activeTaskCacheKey($scheduleKey);
        $now = SchedulerRuntimeHelper::nowUtc();
        $taskId = $this->resolveActiveTaskIdFromCache($cacheKey);

        $task = null;
        if ($taskId !== '') {
            $task = $this->activeTaskStore->findByTaskId($taskId);
        }
        if ($task === null) {
            $task = $this->activeTaskStore->findActiveByScheduleKey($scheduleKey, $now);
        }
        if ($task === null) {
            Cache::forget($cacheKey);

            return false;
        }

        $taskId = trim((string) $task->task_id);
        if ($taskId === '') {
            Cache::forget($cacheKey);

            return false;
        }

        $isBusy = $this->reconcilePersistedActiveTask(
            task: $task,
            cfg: $cfg,
            now: $now,
            writeLog: $writeLog,
        );
        if (! $isBusy) {
            Cache::forget($cacheKey);

            return false;
        }

        Cache::put($cacheKey, ['task_id' => $taskId], now()->addSeconds($cfg['active_task_ttl_sec']));

        return true;
    }

    /**
     * @param  callable(string, string, array<string, mixed>): void  $writeLog
     */
    private function reconcilePersistedActiveTask(
        LaravelSchedulerActiveTask $task,
        array $cfg,
        CarbonImmutable $now,
        callable $writeLog,
        array $prefetchedStatuses = [],
    ): bool {
        $taskId = trim((string) $task->task_id);
        if ($taskId === '') {
            return false;
        }

        $persistedStatus = strtolower(trim((string) $task->status));
        if ($this->isTerminalStatus($persistedStatus)) {
            return false;
        }

        $isExpired = false;
        $persistedExpiresAt = $task->expires_at;
        if ($persistedExpiresAt !== null) {
            $expiresAt = CarbonImmutable::instance($persistedExpiresAt)->utc()->setMicroseconds(0);
            $isExpired = $expiresAt->lt($now);
        }

        $status = array_key_exists($taskId, $prefetchedStatuses)
            ? $prefetchedStatuses[$taskId]
            : $this->fetchTaskStatus($task, $taskId, $cfg);
        // 404 before expiry can be transient read-model lag. Keep task busy until deadline.
        if ($status === 'not_found' && ! $isExpired) {
            $this->activeTaskStore->touchPolledAt($taskId, $now, $status);

            return true;
        }

        if ($status !== null && $this->isTerminalStatus($status)) {
            $this->activeTaskStore->markTerminal(
                taskId: $taskId,
                status: $status,
                terminalAt: $now,
                detailsPatch: [
                    'terminal_source' => 'automation_engine_status_poll',
                ],
                lastPolledAt: $now,
            );
            $this->syncIntentTerminalStatus(
                task: $task,
                terminalStatus: $status,
                terminalSource: 'automation_engine_status_poll',
                now: $now,
            );
            $writeLog(SchedulerRuntimeHelper::scheduleTaskLogName((int) $task->zone_id, (string) $task->task_type), $status === 'completed' ? 'completed' : 'failed', [
                'zone_id' => (int) $task->zone_id,
                'task_type' => (string) $task->task_type,
                'task_id' => $taskId,
                'status' => $status,
                'schedule_key' => (string) $task->schedule_key,
                'correlation_id' => (string) $task->correlation_id,
                'terminal_source' => 'automation_engine_status_poll',
                'terminal_at' => SchedulerRuntimeHelper::toIso($now),
            ]);

            return false;
        }

        if ($isExpired) {
            $taskAgeSec = $this->taskAgeSec($task, $now);
            $hardStaleAfterSec = $this->hardStaleAfterSec($cfg);
            if ($taskAgeSec === null || $taskAgeSec < $hardStaleAfterSec) {
                $this->activeTaskStore->touchPolledAt($taskId, $now, $status);

                return true;
            }

            $terminalStatus = 'timeout';
            $terminalSource = 'laravel_dispatcher_hard_stale_expiry';
            $this->activeTaskStore->markTerminal(
                taskId: $taskId,
                status: $terminalStatus,
                terminalAt: $now,
                detailsPatch: [
                    'terminal_source' => $terminalSource,
                ],
                lastPolledAt: $now,
            );
            $this->syncIntentTerminalStatus(
                task: $task,
                terminalStatus: $terminalStatus,
                terminalSource: $terminalSource,
                now: $now,
            );
            $writeLog(SchedulerRuntimeHelper::scheduleTaskLogName((int) $task->zone_id, (string) $task->task_type), 'failed', [
                'zone_id' => (int) $task->zone_id,
                'task_type' => (string) $task->task_type,
                'task_id' => $taskId,
                'status' => $terminalStatus,
                'schedule_key' => (string) $task->schedule_key,
                'correlation_id' => (string) $task->correlation_id,
                'terminal_source' => $terminalSource,
                'terminal_at' => SchedulerRuntimeHelper::toIso($now),
            ]);

            return false;
        }

        if ($status === null) {
            $this->activeTaskStore->touchPolledAt($taskId, $now, null);

            return true;
        }

        $this->activeTaskStore->touchPolledAt($taskId, $now, $status);

        return true;
    }

    /**
     * @param  \Illuminate\Support\Collection<int, LaravelSchedulerActiveTask>  $pendingTasks
     * @return array<string, string|null> map task_id => normalized status
     */
    private function prefetchAe3IntentStatuses(\Illuminate\Support\Collection $pendingTasks): array
    {
        /** @var array<string, int> $taskIntent */
        $taskIntent = [];
        /** @var array<string, int> $taskZone */
        $taskZone = [];
        /** @var array<int, true> $intentIds */
        $intentIds = [];

        foreach ($pendingTasks as $task) {
            if (! $task instanceof LaravelSchedulerActiveTask) {
                continue;
            }
            if ($this->resolveAutomationRuntime((int) $task->zone_id, 'laravel scheduler task') !== 'ae3') {
                continue;
            }
            $taskId = trim((string) $task->task_id);
            if ($taskId === '') {
                continue;
            }
            $intentId = $this->resolveIntentIdForTask($task);
            if ($intentId <= 0) {
                continue;
            }
            $taskIntent[$taskId] = $intentId;
            $taskZone[$taskId] = (int) $task->zone_id;
            $intentIds[$intentId] = true;
        }

        if ($taskIntent === []) {
            return [];
        }

        try {
            $rows = DB::table('zone_automation_intents')
                ->whereIn('id', array_keys($intentIds))
                ->get(['id', 'zone_id', 'status']);
        } catch (\Throwable $e) {
            Log::warning('Failed to prefetch zone_automation_intents statuses for scheduler poll', [
                'intent_count' => count($intentIds),
                'error' => $e->getMessage(),
                'exception_type' => get_class($e),
            ]);

            return [];
        }

        /** @var array<string, string> $intentStatus */
        $intentStatus = [];
        foreach ($rows as $row) {
            $id = (int) ($row->id ?? 0);
            $zoneId = (int) ($row->zone_id ?? 0);
            if ($id <= 0 || $zoneId <= 0) {
                continue;
            }
            $normalized = match (strtolower(trim((string) ($row->status ?? '')))) {
                'pending', 'claimed', 'running', 'waiting_command' => 'accepted',
                'completed' => 'completed',
                'failed' => 'failed',
                'cancelled' => 'cancelled',
                default => null,
            };
            if ($normalized !== null) {
                $intentStatus[$id.'|'.$zoneId] = $normalized;
            }
        }

        /** @var array<string, string> $result */
        $result = [];
        foreach ($taskIntent as $taskId => $intentId) {
            $zoneId = (int) ($taskZone[$taskId] ?? 0);
            if ($zoneId <= 0) {
                continue;
            }
            $key = $intentId.'|'.$zoneId;
            $result[$taskId] = $intentStatus[$key] ?? 'not_found';
        }

        return $result;
    }

    private function resolveActiveTaskIdFromCache(string $cacheKey): string
    {
        $cached = Cache::get($cacheKey);
        if (is_string($cached)) {
            return trim($cached);
        }
        if (is_array($cached)) {
            return trim((string) ($cached['task_id'] ?? ''));
        }

        return '';
    }

    /**
     * @param  array<string, mixed>  $cfg
     */
    private function fetchTaskStatus(LaravelSchedulerActiveTask $task, string $taskId, array $cfg): ?string
    {
        $taskId = trim($taskId);
        if ($taskId === '') {
            return null;
        }

        if ($this->resolveAutomationRuntime((int) $task->zone_id, 'laravel scheduler task') === 'ae3') {
            return $this->fetchAe3CanonicalTaskStatus($task, $taskId, $cfg);
        }

        if (preg_match('/^intent-(\d+)$/', $taskId, $matches) === 1) {
            $intentId = (int) ($matches[1] ?? 0);
            if ($intentId > 0) {
                try {
                    $intentRow = DB::table('zone_automation_intents')
                        ->where('id', $intentId)
                        ->first(['status']);
                } catch (\Throwable $e) {
                    Log::warning('Failed to load zone_automation_intents status for laravel scheduler task', [
                        'task_id' => $taskId,
                        'intent_id' => $intentId,
                        'zone_id' => (int) $task->zone_id,
                        'error' => $e->getMessage(),
                        'exception_type' => get_class($e),
                    ]);

                    return null;
                }

                if ($intentRow !== null) {
                    $intentStatus = strtolower(trim((string) ($intentRow->status ?? '')));

                    return match ($intentStatus) {
                        'pending', 'claimed', 'running' => 'accepted',
                        'completed' => 'completed',
                        'failed' => 'failed',
                        'cancelled' => 'cancelled',
                        default => null,
                    };
                }

                return 'not_found';
            }
        }

        try {
            /** @var SchedulerLog|null $row */
            $row = SchedulerLog::query()
                ->whereRaw("details->>'task_id' = ?", [$taskId])
                ->orderByDesc('created_at')
                ->orderByDesc('id')
                ->first(['status', 'details']);
        } catch (\Throwable $e) {
            Log::warning('Failed to load scheduler_logs status for laravel scheduler task', [
                'task_id' => $taskId,
                'zone_id' => (int) $task->zone_id,
                'error' => $e->getMessage(),
                'exception_type' => get_class($e),
            ]);

            return null;
        }

        if (! $row) {
            return null;
        }

        $details = is_array($row->details) ? $row->details : [];
        $status = strtolower(trim((string) ($details['status'] ?? $row->status ?? '')));
        if ($status === '') {
            return null;
        }

        return SchedulerConstants::normalizeTerminalStatus($status);
    }

    /**
     * @param  array<string, mixed>  $cfg
     */
    private function fetchAe3CanonicalTaskStatus(
        LaravelSchedulerActiveTask $task,
        string $taskId,
        array $cfg,
    ): ?string {
        if (preg_match('/^\d+$/', $taskId) !== 1) {
            Log::error('AE3 scheduler task_id is not canonical numeric id', [
                'task_id' => $taskId,
                'zone_id' => (int) $task->zone_id,
                'task_type' => (string) $task->task_type,
                'schedule_key' => (string) $task->schedule_key,
            ]);

            return 'not_found';
        }

        // Fast path: read intent status from shared DB (avoids HTTP round-trip to AE).
        $intentId = $this->resolveIntentIdForTask($task);
        if ($intentId > 0) {
            return $this->fetchIntentStatusFromDb($intentId, (int) $task->zone_id);
        }

        Log::warning('AE3 scheduler task has no intent_id in details; marking as not_found', [
            'task_id' => $taskId,
            'zone_id' => (int) $task->zone_id,
            'task_type' => (string) $task->task_type,
            'schedule_key' => (string) $task->schedule_key,
        ]);

        return 'not_found';
    }

    private function fetchIntentStatusFromDb(int $intentId, int $zoneId): ?string
    {
        try {
            $row = DB::table('zone_automation_intents')
                ->where('id', $intentId)
                ->where('zone_id', $zoneId)
                ->first(['status']);
        } catch (\Throwable $e) {
            Log::warning('Failed to read zone_automation_intents status from DB (AE3 fast path)', [
                'intent_id' => $intentId,
                'zone_id' => $zoneId,
                'error' => $e->getMessage(),
            ]);

            return null;
        }

        if ($row === null) {
            return 'not_found';
        }

        return match (strtolower(trim((string) ($row->status ?? '')))) {
            'pending', 'claimed', 'running', 'waiting_command' => 'accepted',
            'completed' => 'completed',
            'failed' => 'failed',
            'cancelled' => 'cancelled',
            default => null,
        };
    }

    private function resolveIntentIdForTask(LaravelSchedulerActiveTask $task): int
    {
        $details = is_array($task->details) ? $task->details : [];
        $intentId = (int) ($details['intent_id'] ?? 0);
        if ($intentId > 0) {
            return $intentId;
        }

        $taskId = trim((string) $task->task_id);
        if (preg_match('/^intent-(\d+)$/', $taskId, $matches) === 1) {
            return (int) ($matches[1] ?? 0);
        }

        return 0;
    }

    private function syncIntentTerminalStatus(
        LaravelSchedulerActiveTask $task,
        string $terminalStatus,
        string $terminalSource,
        CarbonImmutable $now,
    ): void {
        $intentId = $this->resolveIntentIdForTask($task);
        if ($intentId <= 0) {
            return;
        }

        $intentStatus = match ($terminalStatus) {
            'completed' => 'completed',
            'cancelled' => 'cancelled',
            default => 'failed',
        };
        $errorCode = $intentStatus === 'failed' ? 'scheduler_task_'.$terminalStatus : null;
        $errorMessage = $intentStatus === 'failed'
            ? sprintf(
                'Scheduler task %s finished with status %s (%s)',
                trim((string) $task->task_id),
                $terminalStatus,
                $terminalSource,
            )
            : null;

        try {
            DB::table('zone_automation_intents')
                ->where('id', $intentId)
                ->where('zone_id', (int) $task->zone_id)
                ->whereIn('status', ['pending', 'claimed', 'running'])
                ->update([
                    'status' => $intentStatus,
                    'completed_at' => $now,
                    'updated_at' => $now,
                    'error_code' => $errorCode,
                    'error_message' => $errorMessage,
                ]);
        } catch (\Throwable $e) {
            Log::error('Failed to sync zone_automation_intents terminal status from laravel scheduler task', [
                'task_id' => trim((string) $task->task_id),
                'zone_id' => (int) $task->zone_id,
                'intent_id' => $intentId,
                'terminal_status' => $terminalStatus,
                'terminal_source' => $terminalSource,
                'error' => $e->getMessage(),
                'exception_type' => get_class($e),
            ]);
        }
    }

    private function taskAgeSec(LaravelSchedulerActiveTask $task, CarbonImmutable $now): ?int
    {
        $acceptedAt = $task->accepted_at;
        if ($acceptedAt !== null) {
            $startedAt = CarbonImmutable::instance($acceptedAt)->utc()->setMicroseconds(0);

            return max(0, $startedAt->diffInSeconds($now, false));
        }

        $createdAt = $task->created_at;
        if ($createdAt !== null) {
            $startedAt = CarbonImmutable::instance($createdAt)->utc()->setMicroseconds(0);

            return max(0, $startedAt->diffInSeconds($now, false));
        }

        return null;
    }

    /**
     * @param  array<string, mixed>  $cfg
     */
    private function hardStaleAfterSec(array $cfg): int
    {
        $expiresAfterSec = max(1, (int) ($cfg['expires_after_sec'] ?? 600));
        $default = max(900, $expiresAfterSec * 2);

        return max($expiresAfterSec + 1, (int) ($cfg['hard_stale_after_sec'] ?? $default));
    }

    private function isTerminalStatus(string $status): bool
    {
        return in_array($status, SchedulerConstants::TERMINAL_STATUSES, true);
    }
}
