<?php

namespace App\Services\AutomationScheduler;

use App\Models\LaravelSchedulerActiveTask;
use App\Models\SchedulerLog;
use Carbon\CarbonImmutable;
use Illuminate\Support\Facades\Cache;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Http;
use Illuminate\Support\Facades\Log;
use Illuminate\Support\Str;

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
    ): bool {
        $taskId = trim((string) $task->task_id);
        if ($taskId === '') {
            return false;
        }

        $persistedStatus = strtolower(trim((string) $task->status));
        if ($this->isTerminalStatus($persistedStatus)) {
            return false;
        }

        $persistedExpiresAt = $task->expires_at;
        if ($persistedExpiresAt !== null) {
            $expiresAt = CarbonImmutable::instance($persistedExpiresAt)->utc()->setMicroseconds(0);
            if ($expiresAt->lt($now)) {
                $terminalStatus = 'timeout';
                $this->activeTaskStore->markTerminal(
                    taskId: $taskId,
                    status: $terminalStatus,
                    terminalAt: $now,
                    detailsPatch: [
                        'terminal_source' => 'laravel_dispatcher_local_expiry',
                    ],
                    lastPolledAt: $now,
                );
                $writeLog(SchedulerRuntimeHelper::scheduleTaskLogName((int) $task->zone_id, (string) $task->task_type), 'failed', [
                    'zone_id' => (int) $task->zone_id,
                    'task_type' => (string) $task->task_type,
                    'task_id' => $taskId,
                    'status' => $terminalStatus,
                    'schedule_key' => (string) $task->schedule_key,
                    'correlation_id' => (string) $task->correlation_id,
                    'terminal_source' => 'laravel_dispatcher_local_expiry',
                    'terminal_at' => SchedulerRuntimeHelper::toIso($now),
                ]);

                return false;
            }
        }

        $status = $this->fetchTaskStatus($task, $taskId, $cfg);
        if ($status === null) {
            $this->activeTaskStore->touchPolledAt($taskId, $now, null);

            return true;
        }

        if ($this->isTerminalStatus($status)) {
            $this->activeTaskStore->markTerminal(
                taskId: $taskId,
                status: $status,
                terminalAt: $now,
                detailsPatch: [
                    'terminal_source' => 'automation_engine_status_poll',
                ],
                lastPolledAt: $now,
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

        $this->activeTaskStore->touchPolledAt($taskId, $now, $status);

        return true;
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
                        'error' => $e->getMessage(),
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
                'error' => $e->getMessage(),
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
            Log::warning('AE3 scheduler task_id is not canonical numeric id', [
                'task_id' => $taskId,
                'zone_id' => (int) $task->zone_id,
            ]);

            return 'not_found';
        }

        $apiUrl = rtrim((string) ($cfg['api_url'] ?? ''), '/');
        if ($apiUrl === '') {
            return null;
        }

        try {
            $response = Http::acceptJson()
                ->timeout(max(1.0, (float) ($cfg['timeout_sec'] ?? 2.0)))
                ->withHeaders($this->automationEngineHeaders($cfg))
                ->get($apiUrl.'/internal/tasks/'.$taskId);
        } catch (\Throwable $e) {
            Log::warning('Failed to poll AE3 canonical task status from automation-engine', [
                'task_id' => $taskId,
                'zone_id' => (int) $task->zone_id,
                'error' => $e->getMessage(),
            ]);

            return null;
        }

        if ($response->status() === 404) {
            return 'not_found';
        }
        if (! $response->successful()) {
            Log::warning('Unexpected AE3 canonical task status response', [
                'task_id' => $taskId,
                'zone_id' => (int) $task->zone_id,
                'status_code' => $response->status(),
                'response' => $response->body(),
            ]);

            return null;
        }

        $body = $response->json();
        $data = is_array($body) ? ($body['data'] ?? null) : null;
        $status = is_array($data) ? strtolower(trim((string) ($data['status'] ?? ''))) : '';

        return match ($status) {
            'pending', 'claimed', 'running', 'waiting_command' => 'accepted',
            'completed' => 'completed',
            'failed' => 'failed',
            'cancelled' => 'cancelled',
            default => null,
        };
    }

    /**
     * @param  array<string, mixed>  $cfg
     * @return array<string, string>
     */
    private function automationEngineHeaders(array $cfg): array
    {
        $headers = [
            'Accept' => 'application/json',
            'X-Trace-Id' => Str::lower((string) Str::uuid()),
            'X-Scheduler-Id' => (string) ($cfg['scheduler_id'] ?? 'laravel-scheduler'),
        ];

        $token = trim((string) ($cfg['token'] ?? ''));
        if ($token !== '') {
            $headers['Authorization'] = 'Bearer '.$token;
        }

        return $headers;
    }

    private function isTerminalStatus(string $status): bool
    {
        return in_array($status, SchedulerConstants::TERMINAL_STATUSES, true);
    }
}
