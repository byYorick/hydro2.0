<?php

namespace App\Services\AutomationScheduler;

use App\Models\LaravelSchedulerActiveTask;
use Carbon\CarbonImmutable;
use Illuminate\Support\Collection;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Log;

class ActiveTaskStore
{
    /**
     * @param  array<string, mixed>  $details
     */
    public function upsertTaskSnapshot(
        string $taskId,
        int $zoneId,
        string $taskType,
        string $scheduleKey,
        string $correlationId,
        string $status,
        CarbonImmutable $acceptedAt,
        ?CarbonImmutable $dueAt,
        ?CarbonImmutable $expiresAt,
        array $details,
    ): ?LaravelSchedulerActiveTask {
        $taskId = trim($taskId);
        if ($taskId === '' || $zoneId <= 0) {
            return null;
        }

        $normalizedStatus = SchedulerConstants::normalizeTerminalStatus($status);
        $terminalAt = $this->isTerminalStatus($normalizedStatus)
            ? CarbonImmutable::now('UTC')->setMicroseconds(0)
            : null;

        try {
            return LaravelSchedulerActiveTask::query()->updateOrCreate(
                ['task_id' => $taskId],
                [
                    'zone_id' => $zoneId,
                    'task_type' => strtolower(trim($taskType)),
                    'schedule_key' => $scheduleKey,
                    'correlation_id' => $correlationId,
                    'status' => $normalizedStatus,
                    'accepted_at' => $acceptedAt,
                    'due_at' => $dueAt,
                    'expires_at' => $expiresAt,
                    'terminal_at' => $terminalAt,
                    'details' => $details,
                ],
            );
        } catch (\Throwable $e) {
            Log::error('Failed to upsert laravel scheduler active task snapshot', [
                'task_id' => $taskId,
                'zone_id' => $zoneId,
                'schedule_key' => $scheduleKey,
                'status' => $normalizedStatus,
                'error' => $e->getMessage(),
                'exception_type' => get_class($e),
            ]);

            return null;
        }
    }

    public function findByTaskId(string $taskId): ?LaravelSchedulerActiveTask
    {
        $taskId = trim($taskId);
        if ($taskId === '') {
            return null;
        }

        try {
            return LaravelSchedulerActiveTask::query()
                ->where('task_id', $taskId)
                ->first();
        } catch (\Throwable $e) {
            Log::warning('Failed to load laravel scheduler task by task_id', [
                'task_id' => $taskId,
                'error' => $e->getMessage(),
                'exception_type' => get_class($e),
            ]);

            return null;
        }
    }

    public function findByIntentId(int $intentId, int $zoneId): ?LaravelSchedulerActiveTask
    {
        if ($intentId <= 0 || $zoneId <= 0) {
            return null;
        }

        try {
            return LaravelSchedulerActiveTask::query()
                ->where('zone_id', $zoneId)
                ->whereRaw("(details->>'intent_id')::int = ?", [$intentId])
                ->whereNotIn('status', SchedulerConstants::TERMINAL_STATUSES)
                ->orderByDesc('id')
                ->first();
        } catch (\Throwable $e) {
            Log::warning('Failed to load laravel scheduler task by intent_id', [
                'intent_id' => $intentId,
                'zone_id' => $zoneId,
                'error' => $e->getMessage(),
                'exception_type' => get_class($e),
            ]);

            return null;
        }
    }

    /**
     * Returns a map of schedule_key => is_busy for the given keys.
     * Performs a single batched query instead of one per schedule key.
     *
     * @param  list<string>  $scheduleKeys
     * @return array<string, bool>
     */
    public function batchFindBusyScheduleKeys(array $scheduleKeys, CarbonImmutable $now): array
    {
        $scheduleKeys = array_values(array_filter(array_unique(array_map('trim', $scheduleKeys))));
        if ($scheduleKeys === []) {
            return [];
        }

        try {
            $busyKeys = LaravelSchedulerActiveTask::query()
                ->select('schedule_key')
                ->whereIn('schedule_key', $scheduleKeys)
                ->whereNotIn('status', SchedulerConstants::TERMINAL_STATUSES)
                ->where(function ($query) use ($now): void {
                    $query->whereNull('expires_at')
                        ->orWhere('expires_at', '>=', $now);
                })
                ->pluck('schedule_key')
                ->flip()
                ->all();

            $result = [];
            foreach ($scheduleKeys as $key) {
                $result[$key] = isset($busyKeys[$key]);
            }

            return $result;
        } catch (\Throwable $e) {
            Log::warning('Failed to batch-check schedule keys busy status', [
                'count' => count($scheduleKeys),
                'error' => $e->getMessage(),
                'exception_type' => get_class($e),
            ]);

            return [];
        }
    }

    public function findActiveByScheduleKey(string $scheduleKey, CarbonImmutable $now): ?LaravelSchedulerActiveTask
    {
        $scheduleKey = trim($scheduleKey);
        if ($scheduleKey === '') {
            return null;
        }

        try {
            return LaravelSchedulerActiveTask::query()
                ->where('schedule_key', $scheduleKey)
                ->whereNotIn('status', SchedulerConstants::TERMINAL_STATUSES)
                ->where(function ($query) use ($now): void {
                    $query->whereNull('expires_at')
                        ->orWhere('expires_at', '>=', $now);
                })
                ->orderByDesc('accepted_at')
                ->orderByDesc('id')
                ->first();
        } catch (\Throwable $e) {
            Log::warning('Failed to load laravel scheduler active task by schedule key', [
                'schedule_key' => $scheduleKey,
                'error' => $e->getMessage(),
                'exception_type' => get_class($e),
            ]);

            return null;
        }
    }

    /**
     * @return Collection<int, LaravelSchedulerActiveTask>
     */
    public function listPendingForPolling(int $limit = 500): Collection
    {
        $limit = max(1, $limit);

        try {
            return LaravelSchedulerActiveTask::query()
                ->whereNotIn('status', SchedulerConstants::TERMINAL_STATUSES)
                ->orderByRaw('last_polled_at IS NULL DESC')
                ->orderBy('last_polled_at')
                ->orderBy('accepted_at')
                ->limit($limit)
                ->get();
        } catch (\Throwable $e) {
            Log::error('Failed to list laravel scheduler pending tasks for polling', [
                'limit' => $limit,
                'error' => $e->getMessage(),
                'exception_type' => get_class($e),
            ]);

            return collect();
        }
    }

    /**
     * @param  array<string, mixed>  $detailsPatch
     */
    public function markTerminal(
        string $taskId,
        string $status,
        CarbonImmutable $terminalAt,
        array $detailsPatch = [],
        ?CarbonImmutable $lastPolledAt = null,
    ): void {
        $taskId = trim($taskId);
        if ($taskId === '') {
            return;
        }

        $normalizedStatus = SchedulerConstants::normalizeTerminalStatus($status);
        $detailsPatchJson = json_encode($detailsPatch, JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES);
        if (! is_string($detailsPatchJson)) {
            $detailsPatchJson = '{}';
        }
        $terminalStatusPlaceholders = implode(', ', array_fill(0, count(SchedulerConstants::TERMINAL_STATUSES), '?'));

        try {
            $affected = DB::update(
                "
                UPDATE laravel_scheduler_active_tasks
                SET status = ?,
                    terminal_at = ?,
                    last_polled_at = ?,
                    details = COALESCE(details, '{}'::jsonb) || ?::jsonb,
                    updated_at = ?
                WHERE task_id = ?
                  AND status NOT IN ($terminalStatusPlaceholders)
                ",
                [
                    $normalizedStatus,
                    $terminalAt,
                    $lastPolledAt,
                    $detailsPatchJson,
                    $terminalAt,
                    $taskId,
                    ...SchedulerConstants::TERMINAL_STATUSES,
                ],
            );
            if ($affected === 0) {
                Log::debug('markTerminal: no rows updated — task already terminal or not found', [
                    'task_id' => $taskId,
                    'status' => $normalizedStatus,
                ]);
            }
        } catch (\Throwable $e) {
            Log::error('Failed to mark laravel scheduler task as terminal', [
                'task_id' => $taskId,
                'status' => $normalizedStatus,
                'error' => $e->getMessage(),
                'exception_type' => get_class($e),
            ]);
        }
    }

    public function touchPolledAt(string $taskId, CarbonImmutable $polledAt, ?string $status): void
    {
        $taskId = trim($taskId);
        if ($taskId === '') {
            return;
        }

        $updates = ['last_polled_at' => $polledAt];
        $normalizedStatus = SchedulerConstants::normalizeTerminalStatus($status);
        if ($normalizedStatus !== '' && ! $this->isTerminalStatus($normalizedStatus)) {
            $updates['status'] = $normalizedStatus;
        }

        try {
            LaravelSchedulerActiveTask::query()
                ->where('task_id', $taskId)
                ->update($updates);
        } catch (\Throwable $e) {
            Log::warning('Failed to update last_polled_at for laravel scheduler task', [
                'task_id' => $taskId,
                'error' => $e->getMessage(),
                'exception_type' => get_class($e),
            ]);
        }
    }

    public function cleanupTerminalOlderThan(CarbonImmutable $threshold, int $limit): int
    {
        $limit = max(1, $limit);

        try {
            $ids = LaravelSchedulerActiveTask::query()
                ->whereNotNull('terminal_at')
                ->where('terminal_at', '<', $threshold)
                ->orderBy('terminal_at')
                ->limit($limit)
                ->pluck('id')
                ->all();

            if ($ids === []) {
                return 0;
            }

            return LaravelSchedulerActiveTask::query()
                ->whereIn('id', $ids)
                ->delete();
        } catch (\Throwable $e) {
            Log::warning('Failed to cleanup terminal laravel scheduler tasks', [
                'threshold' => $threshold->toIso8601String(),
                'limit' => $limit,
                'error' => $e->getMessage(),
                'exception_type' => get_class($e),
            ]);

            return 0;
        }
    }

    public function countActiveTasks(CarbonImmutable $now): int
    {
        try {
            return LaravelSchedulerActiveTask::query()
                ->whereNotIn('status', SchedulerConstants::TERMINAL_STATUSES)
                ->where(function ($query) use ($now): void {
                    $query->whereNull('expires_at')
                        ->orWhere('expires_at', '>=', $now);
                })
                ->count();
        } catch (\Throwable $e) {
            Log::warning('Failed to count active laravel scheduler tasks', [
                'error' => $e->getMessage(),
                'exception_type' => get_class($e),
            ]);

            return 0;
        }
    }

    private function isTerminalStatus(string $status): bool
    {
        return in_array($status, SchedulerConstants::TERMINAL_STATUSES, true);
    }
}
