<?php

namespace App\Services\AutomationScheduler;

use App\Models\GrowCycle;
use App\Models\SchedulerLog;
use App\Services\EffectiveTargetsService;
use Carbon\CarbonImmutable;
use Illuminate\Http\Client\ConnectionException;
use Illuminate\Support\Facades\Cache;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Http;
use Illuminate\Support\Facades\Log;
use Illuminate\Support\Str;

class SchedulerCycleService
{
    /**
     * @var array<int, array{task_name: string, status: string, details: string, created_at: string}>
     */
    private array $schedulerLogsBuffer = [];

    public function __construct(
        private readonly EffectiveTargetsService $effectiveTargetsService,
        private readonly ActiveTaskStore $activeTaskStore,
        private readonly ZoneCursorStore $zoneCursorStore,
        private readonly LightingScheduleParser $lightingScheduleParser,
        private readonly ActiveTaskPoller $activeTaskPoller,
    ) {}

    /**
     * @param  array<string, mixed>  $cfg
     * @param  array<int, int>  $zoneFilter
     * @return array<string, mixed>
     */
    public function runCycle(array $cfg, array $zoneFilter): array
    {
        $this->schedulerLogsBuffer = [];
        $cycleStartedAt = microtime(true);
        /** @var array<string, int> $dispatchMetrics */
        $dispatchMetrics = [];

        try {
            $this->cleanupTerminalActiveTasks($cfg);

            $traceId = $this->newTraceId();
            if ($cfg['token'] === '') {
                Log::error('Laravel scheduler dispatcher: missing scheduler api token');
                $stats = [
                    'dispatch_mode' => 'start_cycle',
                    'zones_total' => 0,
                    'zones_with_targets' => 0,
                    'schedules_total' => 0,
                    'attempted_dispatches' => 0,
                    'successful_dispatches' => 0,
                    'triggerless_schedules' => 0,
                    'zones_pending_time_retry' => 0,
                    'error' => 'missing_scheduler_api_token',
                ];
                $this->writeSchedulerLog(SchedulerConstants::CYCLE_LOG_TASK_NAME, 'failed', $stats);
                $this->writeCycleMetrics($dispatchMetrics, $stats, $cycleStartedAt);

                return $stats;
            }

            $headers = $this->schedulerHeaders($cfg, $traceId);
            $reconciledBusyness = $this->activeTaskPoller->reconcilePendingActiveTasks(
                cfg: $cfg,
                writeLog: function (string $taskName, string $status, array $details): void {
                    $this->writeSchedulerLog($taskName, $status, $details);
                },
            );
            $zoneIds = $this->loadActiveZoneIds($zoneFilter);

            if ($zoneIds === []) {
                $stats = [
                    'dispatch_mode' => 'start_cycle',
                    'zones_total' => 0,
                    'zones_with_targets' => 0,
                    'schedules_total' => 0,
                    'attempted_dispatches' => 0,
                    'successful_dispatches' => 0,
                    'triggerless_schedules' => 0,
                    'zones_pending_time_retry' => 0,
                ];
                $this->writeSchedulerLog(SchedulerConstants::CYCLE_LOG_TASK_NAME, 'completed', $stats);
                $this->writeCycleMetrics($dispatchMetrics, $stats, $cycleStartedAt);

                return $stats;
            }

            $effectiveTargetsByZone = $this->loadEffectiveTargetsByZone($zoneIds);
            $schedules = [];
            $zonesWithTargets = 0;

            foreach ($zoneIds as $zoneId) {
                $zonePayload = $effectiveTargetsByZone[$zoneId] ?? null;
                if (! is_array($zonePayload)) {
                    continue;
                }
                $targets = $zonePayload['targets'] ?? null;
                if (! is_array($targets)) {
                    continue;
                }

                $zonesWithTargets++;
                foreach ($this->buildSchedulesForZone($zoneId, $targets) as $schedule) {
                    $schedules[] = $schedule;
                }
            }
            $lastRunByTaskName = $this->loadLastRunBatch(
                $this->collectIntervalTaskNames($schedules),
            );

            $attemptedDispatches = 0;
            $successfulDispatches = 0;
            $triggerlessCount = 0;
            $replayBudget = $cfg['catchup_rate_limit_per_cycle'];

            /** @var array<string, bool> $executedKeys */
            $executedKeys = [];
            /** @var array<int, CarbonImmutable> $zoneNow */
            $zoneNow = [];
            /** @var array<int, CarbonImmutable> $zoneLast */
            $zoneLast = [];
            /** @var array<int, bool> $zonesWithPendingTimeDispatch */
            $zonesWithPendingTimeDispatch = [];
            /** @var array<int, bool> $zonesWithSuccessfulTimeDispatch */
            $zonesWithSuccessfulTimeDispatch = [];

            $realNow = $this->nowUtc();
            $context = new ScheduleCycleContext(
                cfg: $cfg,
                headers: $headers,
                traceId: $traceId,
                cycleNow: $realNow,
                lastRunByTaskName: $lastRunByTaskName,
                reconciledBusyness: $reconciledBusyness,
            );
            /** @var array<int, CarbonImmutable> $zoneCursorCache */
            $zoneCursorCache = [];

            foreach ($schedules as $schedule) {
                if (! $schedule instanceof ScheduleItem) {
                    continue;
                }

                $zoneId = $schedule->zoneId;
                $taskType = $schedule->taskType;
                if ($zoneId <= 0 || $taskType === '') {
                    continue;
                }

                $scheduleKey = $schedule->scheduleKey;
                if (isset($executedKeys[$scheduleKey])) {
                    continue;
                }

                if (! isset($zoneNow[$zoneId])) {
                    $zoneNow[$zoneId] = $realNow;
                    $zoneLast[$zoneId] = $this->resolveZoneLastCheck(
                        zoneId: $zoneId,
                        now: $realNow,
                        cursorPersistEnabled: $cfg['cursor_persist_enabled'],
                        zoneCursorCache: $zoneCursorCache,
                    );
                }

                $now = $zoneNow[$zoneId];
                $last = $zoneLast[$zoneId];

                $intervalSec = ScheduleSpecHelper::safePositiveInt($schedule->intervalSec);
                $taskName = SchedulerRuntimeHelper::scheduleTaskLogName($zoneId, $taskType);

                if ($intervalSec > 0) {
                    if ($this->shouldRunIntervalTask($taskName, $intervalSec, $now, $context->lastRunByTaskName)) {
                        $attemptedDispatches++;
                        $dispatchResult = $this->dispatchSchedule(
                            zoneId: $zoneId,
                            schedule: $schedule,
                            triggerTime: $now,
                            scheduleKey: $scheduleKey,
                            context: $context,
                        );
                        $this->incrementDispatchMetric($dispatchMetrics, $zoneId, $taskType, $dispatchResult);
                        if ($dispatchResult['dispatched']) {
                            $successfulDispatches++;
                            $executedKeys[$scheduleKey] = true;
                        }
                    }

                    continue;
                }

                $scheduleTime = $schedule->time;
                if (is_string($scheduleTime) && $scheduleTime !== '') {
                    $crossings = $this->scheduleCrossings($last, $now, $scheduleTime);
                    $plannedTriggers = $this->applyCatchupPolicy($crossings, $now, $cfg['catchup_policy'], $cfg['catchup_max_windows']);
                    $hadDispatchSuccess = false;
                    $hadRetryableFailure = false;
                    $deferredByReplayBudget = false;

                    foreach ($plannedTriggers as $triggerTime) {
                        $isReplay = $triggerTime->lt($now);
                        if ($isReplay) {
                            if ($replayBudget <= 0) {
                                $deferredByReplayBudget = true;
                                break;
                            }
                            $replayBudget--;
                        }

                        $dispatchTrigger = $triggerTime;
                        $dispatchSchedule = $schedule;
                        if ($isReplay) {
                            $dispatchPayload = $schedule->payload;
                            $dispatchPayload['catchup_original_trigger_time'] = $this->toIso($triggerTime);
                            $dispatchPayload['catchup_policy'] = $cfg['catchup_policy'];
                            $dispatchSchedule = $schedule->withPayload($dispatchPayload);

                            if ($now->diffInSeconds($triggerTime) > $cfg['due_grace_sec']) {
                                $dispatchTrigger = $now;
                            }
                        }

                        $attemptedDispatches++;
                        $dispatchResult = $this->dispatchSchedule(
                            zoneId: $zoneId,
                            schedule: $dispatchSchedule,
                            triggerTime: $dispatchTrigger,
                            scheduleKey: $scheduleKey,
                            context: $context,
                        );
                        $this->incrementDispatchMetric($dispatchMetrics, $zoneId, $taskType, $dispatchResult);
                        if ($dispatchResult['dispatched']) {
                            $successfulDispatches++;
                            $hadDispatchSuccess = true;
                            $zonesWithSuccessfulTimeDispatch[$zoneId] = true;
                            break;
                        }
                        if ($dispatchResult['retryable']) {
                            $hadRetryableFailure = true;
                        }
                    }

                    if ($plannedTriggers !== [] && ! $hadDispatchSuccess && ($hadRetryableFailure || $deferredByReplayBudget)) {
                        $zonesWithPendingTimeDispatch[$zoneId] = true;
                    }
                    if ($plannedTriggers !== []) {
                        $executedKeys[$scheduleKey] = true;
                    }

                    continue;
                }

                $startTime = $schedule->startTime;
                $endTime = $schedule->endTime;
                if (is_string($startTime) && is_string($endTime) && $startTime !== '' && $endTime !== '') {
                    $desiredNow = $this->isTimeInWindow($now->format('H:i:s'), $startTime, $endTime);
                    $desiredLast = $this->isTimeInWindow($last->format('H:i:s'), $startTime, $endTime);
                    if ($desiredNow !== $desiredLast) {
                        $attemptedDispatches++;
                        $dispatchResult = $this->dispatchSchedule(
                            zoneId: $zoneId,
                            schedule: $schedule,
                            triggerTime: $now,
                            scheduleKey: $scheduleKey,
                            context: $context,
                        );
                        $this->incrementDispatchMetric($dispatchMetrics, $zoneId, $taskType, $dispatchResult);
                        if ($dispatchResult['dispatched']) {
                            $successfulDispatches++;
                        }
                    }
                    $executedKeys[$scheduleKey] = true;

                    continue;
                }

                $triggerlessCount++;
            }

            $zonesPendingTimeRetry = 0;
            foreach ($zoneNow as $zoneId => $now) {
                $cursorRetryPending = isset($zonesWithPendingTimeDispatch[$zoneId]) && ! isset($zonesWithSuccessfulTimeDispatch[$zoneId]);
                if ($cursorRetryPending) {
                    $zonesPendingTimeRetry++;
                }

                $cursorAt = $cursorRetryPending
                    ? ($zoneLast[$zoneId] ?? $now)
                    : $now;
                $this->persistZoneCursor($zoneId, $cursorAt, $cfg['catchup_policy'], $cfg['cursor_persist_enabled']);
            }

            $stats = [
                'dispatch_mode' => 'start_cycle',
                'zones_total' => count($zoneIds),
                'zones_with_targets' => $zonesWithTargets,
                'schedules_total' => count($schedules),
                'attempted_dispatches' => $attemptedDispatches,
                'successful_dispatches' => $successfulDispatches,
                'triggerless_schedules' => $triggerlessCount,
                'zones_pending_time_retry' => $zonesPendingTimeRetry,
            ];

            $this->writeSchedulerLog(SchedulerConstants::CYCLE_LOG_TASK_NAME, 'completed', $stats);
            $this->writeCycleMetrics($dispatchMetrics, $stats, $cycleStartedAt);

            return $stats;
        } finally {
            $this->flushSchedulerLogsBuffer();
        }
    }

    /**
     * @param  array<string, int>  $dispatchMetrics
     * @param  array{dispatched: bool, retryable: bool, reason: string}  $dispatchResult
     */
    private function incrementDispatchMetric(
        array &$dispatchMetrics,
        int $zoneId,
        string $taskType,
        array $dispatchResult,
    ): void {
        $result = 'not_dispatched';
        if ((bool) ($dispatchResult['dispatched'] ?? false)) {
            $result = 'success';
        } elseif ((bool) ($dispatchResult['retryable'] ?? false)) {
            $result = 'retryable_failed';
        } else {
            $result = 'failed';
        }

        $metricKey = sprintf('%d|%s|%s', $zoneId, $taskType, $result);
        $dispatchMetrics[$metricKey] = (int) ($dispatchMetrics[$metricKey] ?? 0) + 1;
    }

    /**
     * @param  array<string, int>  $dispatchMetrics
     * @param  array<string, mixed>  $stats
     */
    private function writeCycleMetrics(array $dispatchMetrics, array $stats, float $cycleStartedAt): void
    {
        foreach ($dispatchMetrics as $key => $value) {
            [$zoneId, $taskType, $result] = array_pad(explode('|', $key, 3), 3, '');
            $this->writeSchedulerLog(SchedulerConstants::METRICS_LOG_TASK_NAME, 'metric', [
                'metric' => SchedulerConstants::METRIC_DISPATCHES_TOTAL,
                'labels' => [
                    'zone_id' => (int) $zoneId,
                    'task_type' => (string) $taskType,
                    'result' => (string) $result,
                ],
                'value' => (int) $value,
            ]);
        }

        $durationSeconds = max(0.0, microtime(true) - $cycleStartedAt);
        $this->writeSchedulerLog(SchedulerConstants::METRICS_LOG_TASK_NAME, 'metric', [
            'metric' => SchedulerConstants::METRIC_CYCLE_DURATION_SECONDS,
            'labels' => [
                'dispatch_mode' => (string) ($stats['dispatch_mode'] ?? 'start_cycle'),
            ],
            'value' => round($durationSeconds, 6),
        ]);

        $activeTasksCount = $this->activeTaskStore->countActiveTasks($this->nowUtc());
        $this->writeSchedulerLog(SchedulerConstants::METRICS_LOG_TASK_NAME, 'metric', [
            'metric' => SchedulerConstants::METRIC_ACTIVE_TASKS_COUNT,
            'labels' => [
                'dispatch_mode' => (string) ($stats['dispatch_mode'] ?? 'start_cycle'),
            ],
            'value' => $activeTasksCount,
        ]);
    }

    /**
     * @return array{dispatched: bool, retryable: bool, reason: string}
     */
    private function dispatchSchedule(
        int $zoneId,
        ScheduleItem $schedule,
        CarbonImmutable $triggerTime,
        string $scheduleKey,
        ScheduleCycleContext $context,
    ): array {
        $cfg = $context->cfg;
        $headers = $context->headers;

        $taskType = $schedule->taskType;
        if (! in_array($taskType, SchedulerConstants::SUPPORTED_TASK_TYPES, true)) {
            return [
                'dispatched' => false,
                'retryable' => false,
                'reason' => 'unsupported_task_type',
            ];
        }

        if ($this->activeTaskPoller->isScheduleBusy(
            scheduleKey: $scheduleKey,
            cfg: $cfg,
            reconciledBusyness: $context->reconciledBusyness,
            writeLog: function (string $taskName, string $status, array $details): void {
                $this->writeSchedulerLog($taskName, $status, $details);
            },
        )) {
            return [
                'dispatched' => false,
                'retryable' => true,
                'reason' => 'schedule_busy',
            ];
        }

        $taskName = SchedulerRuntimeHelper::scheduleTaskLogName($zoneId, $taskType);
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

        $normalizedStatus = $this->normalizeTerminalStatus($taskStatus);
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
            SchedulerRuntimeHelper::activeTaskCacheKey($scheduleKey),
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
     * @param  array<string, mixed>  $details
     */
    private function writeSchedulerLog(string $taskName, string $status, array $details): void
    {
        if ($status === 'failed') {
            $this->writeSchedulerLogImmediate($taskName, $status, $details);

            return;
        }

        $encoded = json_encode($details, JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES);
        if (! is_string($encoded)) {
            $encoded = '{}';
        }

        $this->schedulerLogsBuffer[] = [
            'task_name' => $taskName,
            'status' => $status,
            'details' => $encoded,
            'created_at' => $this->nowUtc()->toDateTimeString(),
        ];
    }

    /**
     * @param  array<string, mixed>  $details
     */
    private function writeSchedulerLogImmediate(string $taskName, string $status, array $details): void
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

    private function flushSchedulerLogsBuffer(): void
    {
        if ($this->schedulerLogsBuffer === []) {
            return;
        }

        try {
            foreach (array_chunk($this->schedulerLogsBuffer, 500) as $chunk) {
                DB::table('scheduler_logs')->insert($chunk);
            }
        } catch (\Throwable $e) {
            Log::warning('Failed to flush scheduler log buffer from laravel dispatcher', [
                'buffer_size' => count($this->schedulerLogsBuffer),
                'error' => $e->getMessage(),
            ]);
        } finally {
            $this->schedulerLogsBuffer = [];
        }
    }

    /**
     * @param  array<string, mixed>  $cfg
     */
    private function cleanupTerminalActiveTasks(array $cfg): void
    {
        $retentionDays = max(1, (int) ($cfg['active_task_retention_days'] ?? 60));
        $batchLimit = max(1, (int) ($cfg['active_task_cleanup_batch'] ?? 500));
        $threshold = $this->nowUtc()->subDays($retentionDays);
        $deleted = $this->activeTaskStore->cleanupTerminalOlderThan($threshold, $batchLimit);

        if ($deleted > 0) {
            Log::info('Laravel scheduler active task cleanup executed', [
                'deleted' => $deleted,
                'retention_days' => $retentionDays,
                'batch_limit' => $batchLimit,
            ]);
        }
    }

    /**
     * @param  array<int, int>  $zoneFilter
     * @return array<int, int>
     */
    private function loadActiveZoneIds(array $zoneFilter): array
    {
        $query = DB::table('zones')
            ->select('id')
            ->whereIn(DB::raw('lower(status)'), SchedulerConstants::ACTIVE_ZONE_STATUSES_LOWER)
            ->orderBy('id');

        if ($zoneFilter !== []) {
            $query->whereIn('id', $zoneFilter);
        }

        return $query->pluck('id')
            ->map(static fn ($value): int => (int) $value)
            ->filter(static fn (int $value): bool => $value > 0)
            ->values()
            ->all();
    }

    /**
     * @param  array<int, int>  $zoneIds
     * @return array<int, array<string, mixed>>
     */
    private function loadEffectiveTargetsByZone(array $zoneIds): array
    {
        if ($zoneIds === []) {
            return [];
        }

        $cycles = GrowCycle::query()
            ->select(['id', 'zone_id'])
            ->whereIn('zone_id', $zoneIds)
            ->whereIn('status', SchedulerConstants::ACTIVE_CYCLE_STATUSES)
            ->orderByDesc('id')
            ->get();

        if ($cycles->isEmpty()) {
            return [];
        }

        $effectiveByCycleId = $this->effectiveTargetsService->getEffectiveTargetsBatch(
            $cycles->pluck('id')->map(static fn ($value): int => (int) $value)->all()
        );

        $result = [];
        foreach ($cycles as $cycle) {
            $zoneId = (int) $cycle->zone_id;
            if ($zoneId <= 0 || isset($result[$zoneId])) {
                continue;
            }

            $payload = $effectiveByCycleId[(int) $cycle->id] ?? null;
            if (! is_array($payload)) {
                continue;
            }
            if (isset($payload['error'])) {
                continue;
            }
            if (! is_array($payload['targets'] ?? null)) {
                continue;
            }

            $result[$zoneId] = $payload;
        }

        return $result;
    }

    /**
     * @param  array<string, mixed>  $targets
     * @return array<int, ScheduleItem>
     */
    private function buildSchedulesForZone(int $zoneId, array $targets): array
    {
        $schedules = [];

        $irrigation = is_array($targets['irrigation'] ?? null) ? $targets['irrigation'] : [];
        $irrigationSchedule = $targets['irrigation_schedule'] ?? ($irrigation['schedule'] ?? null);
        if ($this->isTaskScheduleEnabled('irrigation', $targets, $irrigation)) {
            foreach ($this->buildGenericTaskSchedules($zoneId, 'irrigation', $irrigation, $irrigationSchedule) as $schedule) {
                $schedules[] = $schedule;
            }
        }

        $lighting = is_array($targets['lighting'] ?? null) ? $targets['lighting'] : [];
        if ($this->isTaskScheduleEnabled('lighting', $targets, $lighting)) {
            $lightingSchedule = $targets['lighting_schedule'] ?? null;
            foreach ($this->lightingScheduleParser->parse($zoneId, $lighting, $lightingSchedule, $this->nowUtc()) as $schedule) {
                $schedules[] = $schedule;
            }
        }

        $genericConfigs = [
            ['ventilation', is_array($targets['ventilation'] ?? null) ? $targets['ventilation'] : [], $targets['ventilation_schedule'] ?? null],
            ['solution_change', is_array($targets['solution_change'] ?? null) ? $targets['solution_change'] : [], $targets['solution_change_schedule'] ?? null],
            ['mist', is_array($targets['mist'] ?? null) ? $targets['mist'] : [], $targets['mist_schedule'] ?? null],
            ['diagnostics', is_array($targets['diagnostics'] ?? null) ? $targets['diagnostics'] : [], $targets['diagnostics_schedule'] ?? null],
        ];

        foreach ($genericConfigs as [$taskType, $config, $scheduleSpec]) {
            if (! $this->isTaskScheduleEnabled((string) $taskType, $targets, (array) $config)) {
                continue;
            }
            $source = $scheduleSpec ?? $config;
            foreach ($this->buildGenericTaskSchedules($zoneId, (string) $taskType, (array) $config, $source) as $schedule) {
                $schedules[] = $schedule;
            }
        }

        return $schedules;
    }

    /**
     * @param  array<string, mixed>  $config
     * @return array<int, ScheduleItem>
     */
    private function buildGenericTaskSchedules(
        int $zoneId,
        string $taskType,
        array $config,
        mixed $scheduleSpec,
    ): array {
        $schedules = [];

        foreach (ScheduleSpecHelper::extractTimeSpecs($scheduleSpec) as $timeSpec) {
            $schedules[] = new ScheduleItem(
                zoneId: $zoneId,
                taskType: $taskType,
                time: $timeSpec,
            );
        }

        $intervalSec = ScheduleSpecHelper::safePositiveInt(
            $config['interval_sec'] ?? ($config['every_sec'] ?? ($config['interval'] ?? null))
        );
        if ($intervalSec > 0) {
            $schedules[] = new ScheduleItem(
                zoneId: $zoneId,
                taskType: $taskType,
                intervalSec: $intervalSec,
            );
        }

        return $schedules;
    }

    /**
     * @param  array<string, mixed>  $targets
     * @param  array<string, mixed>  $config
     */
    private function isTaskScheduleEnabled(string $taskType, array $targets, array $config): bool
    {
        $taskToSubsystem = [
            'irrigation' => 'irrigation',
            'lighting' => 'lighting',
            'ventilation' => 'climate',
            'diagnostics' => 'diagnostics',
            'solution_change' => 'solution_change',
        ];
        $subsystemKey = $taskToSubsystem[$taskType] ?? null;
        if (is_string($subsystemKey)) {
            $enabled = $this->subsystemEnabledFromTargets($targets, $subsystemKey);
            if ($enabled === false) {
                return false;
            }
        }

        $execution = is_array($config['execution'] ?? null) ? $config['execution'] : [];
        if (($execution['force_skip'] ?? false) === true) {
            return false;
        }
        if (($config['force_skip'] ?? false) === true) {
            return false;
        }

        return true;
    }

    /**
     * @param  array<string, mixed>  $targets
     */
    private function subsystemEnabledFromTargets(array $targets, string $subsystemKey): ?bool
    {
        $extensions = $targets['extensions'] ?? null;
        if (! is_array($extensions)) {
            return null;
        }
        $subsystems = $extensions['subsystems'] ?? null;
        if (! is_array($subsystems)) {
            return null;
        }
        $subsystem = $subsystems[$subsystemKey] ?? null;
        if (! is_array($subsystem)) {
            return null;
        }
        $enabled = $subsystem['enabled'] ?? null;

        return is_bool($enabled) ? $enabled : null;
    }

    /**
     * @return array<int, CarbonImmutable>
     */
    private function scheduleCrossings(CarbonImmutable $last, CarbonImmutable $now, string $targetTime): array
    {
        if ($now->lt($last)) {
            [$last, $now] = [$now, $last];
        }

        $startDate = $last->startOfDay();
        $endDate = $now->startOfDay();
        $crossings = [];

        for ($cursor = $startDate; $cursor->lte($endDate); $cursor = $cursor->addDay()) {
            $candidate = CarbonImmutable::createFromFormat(
                'Y-m-d H:i:s',
                $cursor->toDateString().' '.$targetTime,
                'UTC',
            );
            if ($candidate->gt($last) && $candidate->lte($now)) {
                $crossings[] = $candidate;
            }
        }

        return $crossings;
    }

    /**
     * @param  array<int, CarbonImmutable>  $crossings
     * @return array<int, CarbonImmutable>
     */
    private function applyCatchupPolicy(
        array $crossings,
        CarbonImmutable $now,
        string $catchupPolicy,
        int $maxWindows,
    ): array {
        if ($crossings === []) {
            return [];
        }
        if ($catchupPolicy === 'skip') {
            return [$now];
        }
        if ($catchupPolicy === 'replay_limited') {
            return array_slice($crossings, max(0, count($crossings) - $maxWindows));
        }

        return $crossings;
    }

    /**
     * @param  array<string, CarbonImmutable>  $lastRunByTaskName
     */
    private function shouldRunIntervalTask(
        string $taskName,
        int $intervalSec,
        CarbonImmutable $now,
        array $lastRunByTaskName,
    ): bool {
        if ($intervalSec <= 0) {
            return false;
        }

        $lastCompletedAt = $lastRunByTaskName[$taskName] ?? null;
        if (! $lastCompletedAt instanceof CarbonImmutable) {
            return true;
        }

        return $lastCompletedAt->addSeconds($intervalSec)->lte($now);
    }

    /**
     * @param  array<int, ScheduleItem>  $schedules
     * @return array<int, string>
     */
    private function collectIntervalTaskNames(array $schedules): array
    {
        $taskNames = [];

        foreach ($schedules as $schedule) {
            $intervalSec = ScheduleSpecHelper::safePositiveInt($schedule->intervalSec);
            if ($intervalSec <= 0) {
                continue;
            }

            $zoneId = $schedule->zoneId;
            $taskType = $schedule->taskType;
            if ($zoneId <= 0 || $taskType === '') {
                continue;
            }

            $taskNames[] = SchedulerRuntimeHelper::scheduleTaskLogName($zoneId, $taskType);
        }

        return array_values(array_unique($taskNames));
    }

    /**
     * @param  array<int, string>  $taskNames
     * @return array<string, CarbonImmutable>
     */
    private function loadLastRunBatch(array $taskNames): array
    {
        if ($taskNames === []) {
            return [];
        }

        $rows = SchedulerLog::query()
            ->selectRaw('task_name, MAX(created_at) AS last_at')
            ->whereIn('task_name', $taskNames)
            ->whereIn('status', ['completed', 'failed'])
            ->groupBy('task_name')
            ->get();

        $result = [];
        foreach ($rows as $row) {
            $taskName = trim((string) ($row->task_name ?? ''));
            if ($taskName === '') {
                continue;
            }

            $lastAt = $row->last_at ?? null;
            if (! $lastAt) {
                continue;
            }

            try {
                $result[$taskName] = CarbonImmutable::parse((string) $lastAt, 'UTC')->setMicroseconds(0);
            } catch (\Throwable) {
                continue;
            }
        }

        return $result;
    }

    /**
     * @param  array<int, CarbonImmutable>  $zoneCursorCache
     */
    private function resolveZoneLastCheck(
        int $zoneId,
        CarbonImmutable $now,
        bool $cursorPersistEnabled,
        array &$zoneCursorCache,
    ): CarbonImmutable {
        if (isset($zoneCursorCache[$zoneId])) {
            return $zoneCursorCache[$zoneId];
        }

        $default = $now->subSeconds(max(30, (int) config('services.automation_engine.scheduler_dispatch_interval_sec', 60)));
        if (! $cursorPersistEnabled) {
            $zoneCursorCache[$zoneId] = $default;

            return $default;
        }

        $storedCursor = $this->zoneCursorStore->getCursorAt($zoneId);
        if ($storedCursor !== null) {
            $zoneCursorCache[$zoneId] = $storedCursor;

            return $storedCursor;
        }

        $zoneCursorCache[$zoneId] = $default;

        return $default;
    }

    private function persistZoneCursor(int $zoneId, CarbonImmutable $cursorAt, string $catchupPolicy, bool $cursorPersistEnabled): void
    {
        if (! $cursorPersistEnabled) {
            return;
        }

        $this->zoneCursorStore->upsertCursor(
            zoneId: $zoneId,
            cursorAt: $cursorAt,
            catchupPolicy: $catchupPolicy,
            metadata: [
                'source' => 'automation:dispatch-schedules',
            ],
        );

        $taskName = sprintf('scheduler_cursor_zone_%d', $zoneId);
        $this->writeSchedulerLog($taskName, 'cursor', [
            'zone_id' => $zoneId,
            'last_check' => $this->toIso($cursorAt),
            'cursor_at' => $this->toIso($cursorAt),
            'catchup_policy' => $catchupPolicy,
        ]);
    }

    private function isTimeInWindow(string $nowTime, string $startTime, string $endTime): bool
    {
        $now = ScheduleSpecHelper::timeToSeconds($nowTime);
        $start = ScheduleSpecHelper::timeToSeconds($startTime);
        $end = ScheduleSpecHelper::timeToSeconds($endTime);
        if ($now === null || $start === null || $end === null) {
            return false;
        }
        if ($start === $end) {
            return true;
        }
        if ($start < $end) {
            return $now >= $start && $now <= $end;
        }

        return $now >= $start || $now <= $end;
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

    private function normalizeTerminalStatus(string $status): string
    {
        return SchedulerConstants::normalizeTerminalStatus($status);
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

        return $this->normalizeTerminalStatus($status);
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

    /**
     * @param  array<string, mixed>  $cfg
     * @return array<string, string>
     */
    private function schedulerHeaders(array $cfg, string $traceId): array
    {
        $headers = [
            'Accept' => 'application/json',
            'X-Trace-Id' => $traceId,
            'X-Scheduler-Id' => $cfg['scheduler_id'],
        ];

        if ($cfg['token'] !== '') {
            $headers['Authorization'] = 'Bearer '.$cfg['token'];
        }

        return $headers;
    }

    private function newTraceId(): string
    {
        return Str::lower((string) Str::uuid());
    }

    private function toIso(CarbonImmutable $value): string
    {
        return SchedulerRuntimeHelper::toIso($value);
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
        return SchedulerRuntimeHelper::nowUtc();
    }
}
