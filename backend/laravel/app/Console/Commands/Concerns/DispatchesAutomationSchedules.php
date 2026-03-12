<?php

namespace App\Console\Commands\Concerns;

use App\Models\LaravelSchedulerActiveTask;
use App\Models\SchedulerLog;
use App\Services\AutomationScheduler\ScheduleItem;
use App\Services\AutomationScheduler\SchedulerConstants;
use App\Services\ZoneCorrectionConfigService;
use Carbon\CarbonImmutable;
use Illuminate\Http\Client\ConnectionException;
use Illuminate\Support\Facades\Cache;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Http;
use Illuminate\Support\Facades\Log;

/**
 * @deprecated Логика перенесена в App\Services\AutomationScheduler\SchedulerCycleService и ActiveTaskPoller.
 */
trait DispatchesAutomationSchedules
{
    /**
     * @param  array<string, mixed>  $cfg
     * @param  array<string, string>  $headers
     */
    private function reconcilePendingActiveTasks(array $cfg, array $headers): void
    {
        $pollLimit = max(1, (int) ($cfg['active_task_poll_batch'] ?? 500));
        $pendingTasks = $this->activeTaskStore->listPendingForPolling($pollLimit);
        if ($pendingTasks->isEmpty()) {
            return;
        }

        $now = $this->nowUtc();
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
                now: $now,
                cfg: $cfg,
                headers: $headers,
            );

            if ($scheduleKey === '') {
                continue;
            }

            $cacheKey = $this->activeTaskCacheKey($scheduleKey);
            if ($isBusy) {
                Cache::put($cacheKey, ['task_id' => $taskId], now()->addSeconds($cfg['active_task_ttl_sec']));
                continue;
            }

            Cache::forget($cacheKey);
        }
    }

    /**
     * @param  array<string, mixed>  $cfg
     * @param  array<string, string>  $headers
     * @return array{dispatched: bool, retryable: bool, reason: string}
     */
    private function dispatchSchedule(
        int $zoneId,
        ScheduleItem $schedule,
        CarbonImmutable $triggerTime,
        array $cfg,
        array $headers,
    ): array {
        $scheduleKey = $schedule->scheduleKey;
        $taskType = $schedule->taskType;
        if (! in_array($taskType, self::SUPPORTED_TASK_TYPES, true)) {
            return [
                'dispatched' => false,
                'retryable' => false,
                'reason' => 'unsupported_task_type',
            ];
        }

        if ($this->isScheduleBusy($scheduleKey, $cfg, $headers)) {
            return [
                'dispatched' => false,
                'retryable' => true,
                'reason' => 'schedule_busy',
            ];
        }

        $taskName = $this->scheduleTaskLogName($zoneId, $taskType);
        $payload = $schedule->payload;

        $scheduledForIso = $this->toIso($triggerTime);
        $correlationAnchor = $scheduledForIso;
        if (is_string($payload['catchup_original_trigger_time'] ?? null)) {
            $rawCatchupTrigger = (string) $payload['catchup_original_trigger_time'];
            $parsedCatchupTrigger = $this->parseIsoDateTime($rawCatchupTrigger);
            if ($parsedCatchupTrigger !== null) {
                $correlationAnchor = $this->toIso($parsedCatchupTrigger);
            }
        }

        $presetCorrelationId = trim((string) ($payload['correlation_id'] ?? ''));
        $correlationId = $presetCorrelationId !== ''
            ? $presetCorrelationId
            : $this->buildSchedulerCorrelationId(
                zoneId: $zoneId,
                taskType: $taskType,
                scheduledFor: $correlationAnchor,
                scheduleKey: $scheduleKey,
            );

        [$dueAtIso, $expiresAtIso] = $this->computeTaskDeadlines($triggerTime, $cfg['due_grace_sec'], $cfg['expires_after_sec']);
        $acceptedAt = $this->nowUtc();
        $dueAt = $this->parseIsoDateTime($dueAtIso);
        $expiresAt = $this->parseIsoDateTime($expiresAtIso);

        $intentSnapshot = $this->upsertSchedulerIntent(
            zoneId: $zoneId,
            taskType: $taskType,
            correlationId: $correlationId,
            triggerTime: $triggerTime,
        );
        if (! $intentSnapshot['ok']) {
            $this->writeSchedulerLog($taskName, 'failed', [
                'zone_id' => $zoneId,
                'task_type' => $taskType,
                'error' => 'intent_upsert_failed',
                'schedule_key' => $scheduleKey,
                'correlation_id' => $correlationId,
            ]);

            return [
                'dispatched' => false,
                'retryable' => true,
                'reason' => 'intent_upsert_failed',
            ];
        }

        $requestPayload = [
            'source' => 'laravel_scheduler',
            'idempotency_key' => $correlationId,
        ];

        try {
            $response = Http::acceptJson()
                ->timeout($cfg['timeout_sec'])
                ->withHeaders($headers)
                ->post($cfg['api_url'].'/zones/'.$zoneId.'/start-cycle', $requestPayload);
        } catch (ConnectionException $e) {
            $this->writeSchedulerLog($taskName, 'failed', [
                'zone_id' => $zoneId,
                'task_type' => $taskType,
                'error' => 'connection_error',
                'message' => $e->getMessage(),
                'schedule_key' => $scheduleKey,
                'correlation_id' => $correlationId,
            ]);

            return [
                'dispatched' => false,
                'retryable' => true,
                'reason' => 'connection_error',
            ];
        }

        if (! $response->successful()) {
            $this->writeSchedulerLog($taskName, 'failed', [
                'zone_id' => $zoneId,
                'task_type' => $taskType,
                'error' => 'http_error',
                'status_code' => $response->status(),
                'response' => $response->body(),
                'schedule_key' => $scheduleKey,
                'correlation_id' => $correlationId,
            ]);

            return [
                'dispatched' => false,
                'retryable' => true,
                'reason' => 'http_error',
            ];
        }

        $body = $response->json();
        $data = is_array($body) ? ($body['data'] ?? null) : null;
        $taskId = is_array($data) ? trim((string) ($data['task_id'] ?? '')) : '';
        if ($taskId === '' && ($intentSnapshot['intent_id'] ?? null) !== null) {
            $taskId = 'intent-'.(string) $intentSnapshot['intent_id'];
        }
        $apiTaskStatus = is_array($data)
            ? strtolower(trim((string) (($data['task_status'] ?? null) ?? ($data['status'] ?? ''))))
            : '';
        $taskStatus = $this->normalizeSubmittedTaskStatus(
            submittedStatus: $apiTaskStatus,
            accepted: (bool) (is_array($data) ? ($data['accepted'] ?? true) : true),
        );
        $isDuplicate = (bool) (is_array($data) ? ($data['deduplicated'] ?? false) : false);

        if ($taskId === '') {
            $this->writeSchedulerLog($taskName, 'failed', [
                'zone_id' => $zoneId,
                'task_type' => $taskType,
                'error' => 'task_id_missing',
                'response' => $body,
                'schedule_key' => $scheduleKey,
                'correlation_id' => $correlationId,
            ]);

            return [
                'dispatched' => false,
                'retryable' => true,
                'reason' => 'task_id_missing',
            ];
        }

        $normalizedStatus = SchedulerConstants::normalizeTerminalStatus($taskStatus);
        if ($this->isTerminalStatus($normalizedStatus)) {
            $logStatus = $normalizedStatus === 'completed' ? 'completed' : 'failed';
            $terminalDetails = [
                'terminal_on_submit' => true,
                'is_duplicate' => $isDuplicate,
                'scheduled_for' => $scheduledForIso,
                'due_at' => $dueAtIso,
                'expires_at' => $expiresAtIso,
                'schedule_key' => $scheduleKey,
                'correlation_id' => $correlationId,
                'accepted_at' => $this->toIso($acceptedAt),
            ];
            $this->writeSchedulerLog($taskName, $logStatus, [
                'zone_id' => $zoneId,
                'task_type' => $taskType,
                'task_id' => $taskId,
                'status' => $normalizedStatus,
                ...$terminalDetails,
            ]);
            $this->persistActiveTaskSnapshot(
                zoneId: $zoneId,
                taskId: $taskId,
                taskType: $taskType,
                scheduleKey: $scheduleKey,
                correlationId: $correlationId,
                status: $normalizedStatus,
                acceptedAt: $acceptedAt,
                dueAt: $dueAt,
                expiresAt: $expiresAt,
                details: $terminalDetails,
            );

            return [
                'dispatched' => $normalizedStatus === 'completed',
                'retryable' => false,
                'reason' => 'terminal_'.$normalizedStatus,
            ];
        }

        $acceptedDetails = [
            'deduplicated' => $isDuplicate,
            'intent_id' => $intentSnapshot['intent_id'] ?? null,
            'scheduled_for' => $scheduledForIso,
            'due_at' => $dueAtIso,
            'expires_at' => $expiresAtIso,
            'schedule_key' => $scheduleKey,
            'correlation_id' => $correlationId,
            'accepted_at' => $this->toIso($acceptedAt),
        ];

        $this->writeSchedulerLog($taskName, 'accepted', [
            'zone_id' => $zoneId,
            'task_type' => $taskType,
            'task_id' => $taskId,
            'status' => $taskStatus,
            ...$acceptedDetails,
        ]);
        $this->persistActiveTaskSnapshot(
            zoneId: $zoneId,
            taskId: $taskId,
            taskType: $taskType,
            scheduleKey: $scheduleKey,
            correlationId: $correlationId,
            status: $taskStatus,
            acceptedAt: $acceptedAt,
            dueAt: $dueAt,
            expiresAt: $expiresAt,
            details: $acceptedDetails,
        );

        Cache::put(
            $this->activeTaskCacheKey($scheduleKey),
            [
                'task_id' => $taskId,
                'zone_id' => $zoneId,
                'task_type' => $taskType,
                'accepted_at' => $this->toIso($acceptedAt),
            ],
            now()->addSeconds($cfg['active_task_ttl_sec']),
        );

        return [
            'dispatched' => true,
            'retryable' => false,
            'reason' => 'accepted',
        ];
    }

    /**
     * @param  array<string, mixed>  $cfg
     * @param  array<string, string>  $headers
     */
    private function isScheduleBusy(string $scheduleKey, array $cfg, array $headers): bool
    {
        $cacheKey = $this->activeTaskCacheKey($scheduleKey);
        $now = $this->nowUtc();
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
            now: $now,
            cfg: $cfg,
            headers: $headers,
        );
        if (! $isBusy) {
            Cache::forget($cacheKey);

            return false;
        }

        Cache::put($cacheKey, ['task_id' => $taskId], now()->addSeconds($cfg['active_task_ttl_sec']));

        return true;
    }

    /**
     * @param  array<string, mixed>  $cfg
     * @param  array<string, string>  $headers
     */
    private function reconcilePersistedActiveTask(
        LaravelSchedulerActiveTask $task,
        CarbonImmutable $now,
        array $cfg,
        array $headers,
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
                $this->writeSchedulerLog($this->scheduleTaskLogName((int) $task->zone_id, (string) $task->task_type), 'failed', [
                    'zone_id' => (int) $task->zone_id,
                    'task_type' => (string) $task->task_type,
                    'task_id' => $taskId,
                    'status' => $terminalStatus,
                    'schedule_key' => (string) $task->schedule_key,
                    'correlation_id' => (string) $task->correlation_id,
                    'terminal_source' => 'laravel_dispatcher_local_expiry',
                    'terminal_at' => $this->toIso($now),
                ]);

                return false;
            }
        }

        $status = $this->fetchTaskStatus($taskId, $cfg, $headers);
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
            $this->writeSchedulerLog($this->scheduleTaskLogName((int) $task->zone_id, (string) $task->task_type), $status === 'completed' ? 'completed' : 'failed', [
                'zone_id' => (int) $task->zone_id,
                'task_type' => (string) $task->task_type,
                'task_id' => $taskId,
                'status' => $status,
                'schedule_key' => (string) $task->schedule_key,
                'correlation_id' => (string) $task->correlation_id,
                'terminal_source' => 'automation_engine_status_poll',
                'terminal_at' => $this->toIso($now),
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
     * @param  array<string, mixed>  $details
     */
    private function persistActiveTaskSnapshot(
        int $zoneId,
        string $taskId,
        string $taskType,
        string $scheduleKey,
        string $correlationId,
        string $status,
        CarbonImmutable $acceptedAt,
        ?CarbonImmutable $dueAt,
        ?CarbonImmutable $expiresAt,
        array $details,
    ): void {
        $this->activeTaskStore->upsertTaskSnapshot(
            taskId: $taskId,
            zoneId: $zoneId,
            taskType: $taskType,
            scheduleKey: $scheduleKey,
            correlationId: $correlationId,
            status: $status,
            acceptedAt: $acceptedAt,
            dueAt: $dueAt,
            expiresAt: $expiresAt,
            details: $details,
        );
    }

    /**
     * @param  array<string, mixed>  $cfg
     * @param  array<string, string>  $headers
     */
    private function fetchTaskStatus(string $taskId, array $cfg, array $headers): ?string
    {
        $taskId = trim($taskId);
        if ($taskId === '') {
            return null;
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

    private function activeTaskCacheKey(string $scheduleKey): string
    {
        return 'laravel_scheduler_active:'.sha1($scheduleKey);
    }

    private function scheduleTaskLogName(int $zoneId, string $taskType): string
    {
        return sprintf('%s_%s_zone_%d', self::TASK_NAME_PREFIX, $taskType, $zoneId);
    }

    private function normalizeSubmittedTaskStatus(string $submittedStatus, bool $accepted): string
    {
        $status = strtolower(trim($submittedStatus));
        if ($status === '') {
            return $accepted ? 'accepted' : 'rejected';
        }

        if (in_array($status, ['pending', 'claimed', 'running', 'accepted', 'queued'], true)) {
            return 'accepted';
        }

        return SchedulerConstants::normalizeTerminalStatus($status);
    }

    private function isTerminalStatus(string $status): bool
    {
        return in_array($status, SchedulerConstants::TERMINAL_STATUSES, true);
    }

    private function buildSchedulerCorrelationId(
        int $zoneId,
        string $taskType,
        ?string $scheduledFor,
        ?string $scheduleKey,
    ): string {
        $base = sprintf(
            '%d|%s|%s|%s',
            $zoneId,
            $taskType,
            $scheduledFor ?? '',
            $scheduleKey ?? '',
        );
        $digest = substr(hash('sha256', $base), 0, 20);

        return sprintf('sch:z%d:%s:%s', $zoneId, $taskType, $digest);
    }

    /**
     * @return array{ok: bool, intent_id: int|null}
     */
    private function upsertSchedulerIntent(
        int $zoneId,
        string $taskType,
        string $correlationId,
        CarbonImmutable $triggerTime,
    ): array {
        try {
            app(ZoneCorrectionConfigService::class)->ensureDefaultForZone($zoneId);

            $intentPayload = [
                'source' => 'laravel_scheduler',
                'workflow' => 'cycle_start',
            ];
            $intentType = $this->mapTaskTypeToIntentType($taskType);
            $now = $this->nowUtc();

            $row = DB::selectOne(
                "
                INSERT INTO zone_automation_intents (
                    zone_id,
                    intent_type,
                    payload,
                    idempotency_key,
                    status,
                    not_before,
                    retry_count,
                    max_retries,
                    created_at,
                    updated_at
                )
                VALUES (?, ?, ?::jsonb, ?, 'pending', ?, 0, 3, ?, ?)
                ON CONFLICT (idempotency_key)
                DO UPDATE SET
                    payload = EXCLUDED.payload,
                    not_before = EXCLUDED.not_before,
                    updated_at = EXCLUDED.updated_at
                RETURNING id
                ",
                [
                    $zoneId,
                    $intentType,
                    json_encode($intentPayload, JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES),
                    $correlationId,
                    $triggerTime,
                    $now,
                    $now,
                ],
            );
            $intentId = isset($row->id) ? (int) $row->id : null;

            return ['ok' => true, 'intent_id' => $intentId];
        } catch (\Throwable $e) {
            Log::warning('Failed to upsert scheduler intent', [
                'zone_id' => $zoneId,
                'task_type' => $taskType,
                'correlation_id' => $correlationId,
                'error' => $e->getMessage(),
            ]);

            return ['ok' => false, 'intent_id' => null];
        }
    }

    private function mapTaskTypeToIntentType(string $taskType): string
    {
        // intent_type is stored for audit/debug; automation-engine executes start-cycle as diagnostics/cycle_start.
        $normalized = strtolower(trim($taskType));

        return match ($normalized) {
            'irrigation' => 'IRRIGATE_ONCE',
            'lighting' => 'LIGHTING_TICK',
            'ventilation' => 'VENTILATION_TICK',
            'solution_change' => 'SOLUTION_CHANGE_TICK',
            'mist' => 'MIST_TICK',
            default => 'DIAGNOSTICS_TICK',
        };
    }

    /**
     * @return array{0:string,1:string}
     */
    private function computeTaskDeadlines(CarbonImmutable $scheduledFor, int $dueGraceSec, int $expiresAfterSec): array
    {
        $dueAt = $scheduledFor->addSeconds($dueGraceSec);
        $expiresAt = $scheduledFor->addSeconds($expiresAfterSec);

        return [$this->toIso($dueAt), $this->toIso($expiresAt)];
    }

    private function toIso(CarbonImmutable $value): string
    {
        return $value->format('Y-m-d\TH:i:s\Z');
    }

    private function parseIsoDateTime(?string $value): ?CarbonImmutable
    {
        if (! is_string($value) || trim($value) === '') {
            return null;
        }

        try {
            return CarbonImmutable::parse($value)->utc()->setMicroseconds(0);
        } catch (\Throwable) {
            return null;
        }
    }

    private function nowUtc(): CarbonImmutable
    {
        return CarbonImmutable::now('UTC')->setMicroseconds(0);
    }

    /**
     * @param  array<string, mixed>  $details
     */
    private function writeSchedulerLog(string $taskName, string $status, array $details): void
    {
        try {
            SchedulerLog::query()->create([
                'task_name' => $taskName,
                'status' => $status,
                'details' => $details,
            ]);
        } catch (\Throwable $e) {
            Log::warning('Failed to write scheduler log from laravel dispatcher', [
                'task_name' => $taskName,
                'status' => $status,
                'error' => $e->getMessage(),
            ]);
        }
    }
}
