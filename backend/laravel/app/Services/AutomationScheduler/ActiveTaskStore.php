<?php

namespace App\Services\AutomationScheduler;

use App\Models\LaravelSchedulerActiveTask;
use Carbon\CarbonImmutable;
use Illuminate\Support\Facades\Log;

class ActiveTaskStore
{
    private const TERMINAL_STATUSES = [
        'completed',
        'done',
        'failed',
        'rejected',
        'expired',
        'timeout',
        'error',
        'not_found',
    ];

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

        $normalizedStatus = $this->normalizeStatus($status);
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
            Log::warning('Failed to upsert laravel scheduler active task snapshot', [
                'task_id' => $taskId,
                'zone_id' => $zoneId,
                'status' => $normalizedStatus,
                'error' => $e->getMessage(),
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
            ]);

            return null;
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
                ->whereNotIn('status', self::TERMINAL_STATUSES)
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
            ]);

            return null;
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
        $task = $this->findByTaskId($taskId);
        if (! $task) {
            return;
        }

        $normalizedStatus = $this->normalizeStatus($status);
        $details = is_array($task->details) ? $task->details : [];
        $details = array_merge($details, $detailsPatch);

        try {
            $task->fill([
                'status' => $normalizedStatus,
                'terminal_at' => $terminalAt,
                'last_polled_at' => $lastPolledAt,
                'details' => $details,
            ]);
            $task->save();
        } catch (\Throwable $e) {
            Log::warning('Failed to mark laravel scheduler task as terminal', [
                'task_id' => $taskId,
                'status' => $normalizedStatus,
                'error' => $e->getMessage(),
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
        $normalizedStatus = $this->normalizeStatus($status);
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
                'error' => $e->getMessage(),
            ]);

            return 0;
        }
    }

    private function normalizeStatus(?string $status): string
    {
        $normalized = strtolower(trim((string) $status));
        if ($normalized === 'done') {
            return 'completed';
        }
        if ($normalized === 'error') {
            return 'failed';
        }

        return $normalized;
    }

    private function isTerminalStatus(string $status): bool
    {
        return in_array($status, self::TERMINAL_STATUSES, true);
    }
}

