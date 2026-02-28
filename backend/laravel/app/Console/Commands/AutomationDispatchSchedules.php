<?php

namespace App\Console\Commands;

use App\Console\Commands\Concerns\BuildsAutomationDispatchSchedules;
use App\Console\Commands\Concerns\ConfiguresAutomationDispatch;
use App\Console\Commands\Concerns\DispatchesAutomationSchedules;
use App\Services\AutomationScheduler\ActiveTaskStore;
use App\Services\AutomationScheduler\ZoneCursorStore;
use App\Services\EffectiveTargetsService;
use Carbon\CarbonImmutable;
use Illuminate\Console\Command;
use Illuminate\Support\Facades\Log;

class AutomationDispatchSchedules extends Command
{
    use BuildsAutomationDispatchSchedules;
    use ConfiguresAutomationDispatch;
    use DispatchesAutomationSchedules;

    protected $signature = 'automation:dispatch-schedules {--zone-id=* : Ограничить dispatch указанными zone_id}';

    protected $description = 'Laravel scheduler dispatcher: планирование и отправка abstract scheduler задач в automation-engine';

    private const ACTIVE_ZONE_STATUSES = ['online', 'warning', 'RUNNING', 'PAUSED'];

    private const ACTIVE_CYCLE_STATUSES = ['PLANNED', 'RUNNING', 'PAUSED'];

    private const SUPPORTED_TASK_TYPES = [
        'irrigation',
        'lighting',
        'ventilation',
        'solution_change',
        'mist',
        'diagnostics',
    ];

    private const CATCHUP_POLICIES = ['skip', 'replay_limited', 'replay_all'];

    private const TERMINAL_STATUSES = ['completed', 'done', 'failed', 'rejected', 'expired', 'timeout', 'error', 'cancelled', 'not_found'];

    private const TASK_NAME_PREFIX = 'laravel_scheduler_task';

    private const CYCLE_LOG_TASK_NAME = 'laravel_scheduler_cycle';

    /**
     * @var array<int, CarbonImmutable>
     */
    private array $zoneCursorCache = [];

    public function __construct(
        private readonly EffectiveTargetsService $effectiveTargetsService,
        private readonly ActiveTaskStore $activeTaskStore,
        private readonly ZoneCursorStore $zoneCursorStore,
    ) {
        parent::__construct();
    }

    public function handle(): int
    {
        if (! $this->isDispatcherEnabled()) {
            $this->line('AUTOMATION_LARAVEL_SCHEDULER_ENABLED=0, dispatch skipped.');

            return self::SUCCESS;
        }

        $zoneFilter = collect($this->option('zone-id'))
            ->map(static fn ($value): int => (int) $value)
            ->filter(static fn (int $value): bool => $value > 0)
            ->unique()
            ->values()
            ->all();

        $lock = $this->acquireDispatchLock();
        if (! $lock) {
            Log::info('Laravel scheduler dispatcher skipped due to active lock');
            $this->line('Dispatch lock already acquired, skip current cycle.');

            return self::SUCCESS;
        }

        try {
            $stats = $this->dispatchCycle($zoneFilter);
            $this->line(sprintf(
                'Dispatch cycle finished: zones=%d schedules=%d attempted=%d success=%d pending_retry=%d',
                (int) ($stats['zones_total'] ?? 0),
                (int) ($stats['schedules_total'] ?? 0),
                (int) ($stats['attempted_dispatches'] ?? 0),
                (int) ($stats['successful_dispatches'] ?? 0),
                (int) ($stats['zones_pending_time_retry'] ?? 0),
            ));

            return self::SUCCESS;
        } finally {
            try {
                $lock->release();
            } catch (\Throwable $e) {
                Log::warning('Laravel scheduler dispatcher failed to release lock', [
                    'error' => $e->getMessage(),
                ]);
            }
        }
    }

    /**
     * @param  array<int, int>  $zoneFilter
     * @return array<string, mixed>
     */
    private function dispatchCycle(array $zoneFilter): array
    {
        $cfg = $this->schedulerConfig();
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
            $this->writeSchedulerLog(self::CYCLE_LOG_TASK_NAME, 'failed', $stats);

            return $stats;
        }

        $headers = $this->schedulerHeaders($cfg, $traceId);
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
            $this->writeSchedulerLog(self::CYCLE_LOG_TASK_NAME, 'completed', $stats);

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

        foreach ($schedules as $schedule) {
            $zoneId = (int) ($schedule['zone_id'] ?? 0);
            $taskType = strtolower((string) ($schedule['type'] ?? ''));
            if ($zoneId <= 0 || $taskType === '') {
                continue;
            }

            $scheduleKey = $this->buildScheduleKey($zoneId, $schedule);
            if (isset($executedKeys[$scheduleKey])) {
                continue;
            }

            if (! isset($zoneNow[$zoneId])) {
                $zoneNow[$zoneId] = $realNow;
                $zoneLast[$zoneId] = $this->resolveZoneLastCheck($zoneId, $realNow, $cfg['cursor_persist_enabled']);
            }

            $now = $zoneNow[$zoneId];
            $last = $zoneLast[$zoneId];

            $intervalSec = $this->safePositiveInt($schedule['interval_sec'] ?? null);
            $taskName = $this->scheduleTaskLogName($zoneId, $taskType);

            if ($intervalSec > 0) {
                if ($this->shouldRunIntervalTask($taskName, $intervalSec, $now)) {
                    $attemptedDispatches++;
                    $dispatchResult = $this->dispatchSchedule(
                        zoneId: $zoneId,
                        schedule: $schedule,
                        triggerTime: $now,
                        scheduleKey: $scheduleKey,
                        cfg: $cfg,
                        headers: $headers,
                    );
                    if ($dispatchResult['dispatched']) {
                        $successfulDispatches++;
                        $executedKeys[$scheduleKey] = true;
                    }
                }

                continue;
            }

            $scheduleTime = $schedule['time'] ?? null;
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
                        $dispatchPayload = is_array($schedule['payload'] ?? null)
                            ? $schedule['payload']
                            : [];
                        $dispatchPayload['catchup_original_trigger_time'] = $this->toIso($triggerTime);
                        $dispatchPayload['catchup_policy'] = $cfg['catchup_policy'];
                        $dispatchSchedule['payload'] = $dispatchPayload;

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
                        cfg: $cfg,
                        headers: $headers,
                    );
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

            $startTime = $schedule['start_time'] ?? null;
            $endTime = $schedule['end_time'] ?? null;
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
                        cfg: $cfg,
                        headers: $headers,
                    );
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
            $this->zoneCursorCache[$zoneId] = $cursorAt;
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

        $this->writeSchedulerLog(self::CYCLE_LOG_TASK_NAME, 'completed', $stats);

        return $stats;
    }
}
