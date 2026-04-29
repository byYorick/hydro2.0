<?php

namespace App\Services\AutomationScheduler;

use App\Models\SchedulerLog;
use Carbon\CarbonImmutable;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Log;
use Illuminate\Support\Str;

class SchedulerCycleOrchestrator
{
    private const BACKPRESSURE_REASONS = [
        'schedule_busy',
        'zone_setup_pending',
        'start_cycle_zone_busy',
        'start_irrigation_zone_busy',
        'start_lighting_tick_zone_busy',
    ];

    /**
     * @var array<int, array{task_name: string, status: string, details: string, created_at: string}>
     */
    private array $schedulerLogsBuffer = [];

    public function __construct(
        private readonly ScheduleLoader $scheduleLoader,
        private readonly ScheduleDispatcher $scheduleDispatcher,
        private readonly SchedulerCycleFinalizer $finalizer,
        private readonly ZoneScheduleItemBuilder $zoneScheduleItemBuilder,
        private readonly ActiveTaskPoller $activeTaskPoller,
        private readonly ActiveTaskStore $activeTaskStore,
        private readonly SchedulerMetricsStore $schedulerMetricsStore,
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
            $this->finalizer->cleanupTerminalActiveTasks($cfg);

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
            $zoneIds = $this->scheduleLoader->loadActiveZoneIds($zoneFilter);
            $zoneWorkflowPhases = [];

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

            if ($zoneIds !== []) {
                $workflowRows = DB::table('zone_workflow_state')
                    ->select(['zone_id', 'workflow_phase'])
                    ->whereIn('zone_id', $zoneIds)
                    ->get();
                foreach ($workflowRows as $workflowRow) {
                    $zoneKey = (int) ($workflowRow->zone_id ?? 0);
                    if ($zoneKey <= 0) {
                        continue;
                    }
                    $zoneWorkflowPhases[$zoneKey] = strtolower(trim((string) ($workflowRow->workflow_phase ?? '')));
                }
            }

            $effectiveTargetsByZone = $this->scheduleLoader->loadEffectiveTargetsByZone($zoneIds);
            $schedules = [];
            $zonesWithTargets = 0;
            $realNow = SchedulerRuntimeHelper::nowUtc();

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
                foreach ($this->zoneScheduleItemBuilder->buildSchedulesForZone($zoneId, $targets, $realNow) as $schedule) {
                    $schedules[] = $schedule;
                }
            }
            $lastRunByTaskName = $this->scheduleLoader->loadLastRunBatch(
                $this->scheduleLoader->collectIntervalTaskNames($schedules),
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

            // Batch-prefetch busy status for schedule_keys not yet covered by
            // reconcilePendingActiveTasks() (limited to 500 rows). Without this,
            // isScheduleBusy() fires 1-2 DB queries per schedule in the hot loop.
            $unresolvedKeys = [];
            foreach ($schedules as $schedule) {
                if ($schedule instanceof ScheduleItem) {
                    $key = $schedule->scheduleKey;
                    if ($key !== '' && ! array_key_exists($key, $reconciledBusyness)) {
                        $unresolvedKeys[] = $key;
                    }
                }
            }
            if ($unresolvedKeys !== []) {
                $batchBusyness = $this->activeTaskStore->batchFindBusyScheduleKeys(
                    array_unique($unresolvedKeys),
                    $realNow,
                );
                $reconciledBusyness = array_merge($reconciledBusyness, $batchBusyness);
            }

            $context = new ScheduleCycleContext(
                cfg: $cfg,
                headers: $headers,
                traceId: $traceId,
                cycleNow: $realNow,
                lastRunByTaskName: $lastRunByTaskName,
                reconciledBusyness: $reconciledBusyness,
                zoneWorkflowPhases: $zoneWorkflowPhases,
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
                    $zoneLast[$zoneId] = $this->scheduleLoader->resolveZoneLastCheck(
                        zoneId: $zoneId,
                        now: $realNow,
                        dispatchIntervalSec: max(10, (int) ($cfg['dispatch_interval_sec'] ?? 60)),
                        cursorPersistEnabled: $cfg['cursor_persist_enabled'],
                        zoneCursorCache: $zoneCursorCache,
                    );
                }

                $now = $zoneNow[$zoneId];
                $last = $zoneLast[$zoneId];

                $intervalSec = ScheduleSpecHelper::safePositiveInt($schedule->intervalSec);
                $taskName = SchedulerRuntimeHelper::scheduleTaskLogName($zoneId, $taskType);

                if ($intervalSec > 0) {
                    if ($this->finalizer->shouldRunIntervalTask($taskName, $intervalSec, $now, $context->lastRunByTaskName)) {
                        $attemptedDispatches++;
                        $dispatchResult = $this->scheduleDispatcher->dispatch(
                            zoneId: $zoneId,
                            schedule: $schedule,
                            triggerTime: $now,
                            scheduleKey: $scheduleKey,
                            context: $context,
                            writeLog: function (string $taskName, string $status, array $details): void {
                                $this->writeSchedulerLog($taskName, $status, $details);
                            },
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
                    $crossings = $this->finalizer->scheduleCrossings($last, $now, $scheduleTime);
                    $plannedTriggers = $this->finalizer->applyCatchupPolicy($crossings, $now, $cfg['catchup_policy'], $cfg['catchup_max_windows']);
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
                            $dispatchPayload['catchup_original_trigger_time'] = SchedulerRuntimeHelper::toIso($triggerTime);
                            $dispatchPayload['catchup_policy'] = $cfg['catchup_policy'];
                            $dispatchSchedule = $schedule->withPayload($dispatchPayload);

                            if ($now->diffInSeconds($triggerTime) > $cfg['due_grace_sec']) {
                                $dispatchTrigger = $now;
                            }
                        }

                        $attemptedDispatches++;
                        $dispatchResult = $this->scheduleDispatcher->dispatch(
                            zoneId: $zoneId,
                            schedule: $dispatchSchedule,
                            triggerTime: $dispatchTrigger,
                            scheduleKey: $scheduleKey,
                            context: $context,
                            writeLog: function (string $taskName, string $status, array $details): void {
                                $this->writeSchedulerLog($taskName, $status, $details);
                            },
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
                    $desiredNow = $this->finalizer->isTimeInWindow($now->format('H:i:s'), $startTime, $endTime);
                    $desiredLast = $this->finalizer->isTimeInWindow($last->format('H:i:s'), $startTime, $endTime);
                    if ($desiredNow !== $desiredLast) {
                        $attemptedDispatches++;
                        $dispatchResult = $this->scheduleDispatcher->dispatch(
                            zoneId: $zoneId,
                            schedule: $schedule,
                            triggerTime: $now,
                            scheduleKey: $scheduleKey,
                            context: $context,
                            writeLog: function (string $taskName, string $status, array $details): void {
                                $this->writeSchedulerLog($taskName, $status, $details);
                            },
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
                $this->finalizer->persistZoneCursor(
                    $zoneId,
                    $cursorAt,
                    $cfg['catchup_policy'],
                    $cfg['cursor_persist_enabled'],
                    function (string $taskName, string $status, array $details): void {
                        $this->writeSchedulerLog($taskName, $status, $details);
                    },
                );
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
        $reason = (string) ($dispatchResult['reason'] ?? '');
        $result = 'not_dispatched';
        if ((bool) ($dispatchResult['dispatched'] ?? false)) {
            $result = 'success';
        } elseif (in_array($reason, self::BACKPRESSURE_REASONS, true)) {
            $result = 'backpressure';
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
        $this->schedulerMetricsStore->recordDispatchTotals($dispatchMetrics);

        $durationSeconds = max(0.0, microtime(true) - $cycleStartedAt);
        $dispatchMode = (string) ($stats['dispatch_mode'] ?? 'start_cycle');
        $this->schedulerMetricsStore->observeCycleDuration($dispatchMode, $durationSeconds);

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

        $this->writeSchedulerLog(SchedulerConstants::METRICS_LOG_TASK_NAME, 'metric', [
            'metric' => SchedulerConstants::METRIC_CYCLE_DURATION_SECONDS,
            'labels' => [
                'dispatch_mode' => $dispatchMode,
            ],
            'value' => round($durationSeconds, 6),
        ]);

        $activeTasksCount = $this->activeTaskStore->countActiveTasks(SchedulerRuntimeHelper::nowUtc());
        $this->writeSchedulerLog(SchedulerConstants::METRICS_LOG_TASK_NAME, 'metric', [
            'metric' => SchedulerConstants::METRIC_ACTIVE_TASKS_COUNT,
            'labels' => [
                'dispatch_mode' => (string) ($stats['dispatch_mode'] ?? 'start_cycle'),
            ],
            'value' => $activeTasksCount,
        ]);
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
            'created_at' => SchedulerRuntimeHelper::nowUtc()->toDateTimeString(),
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
}
