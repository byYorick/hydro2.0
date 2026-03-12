<?php

namespace App\Services\AutomationScheduler;

use Carbon\CarbonImmutable;
use Illuminate\Support\Facades\Log;

class SchedulerCycleFinalizer
{
    public function __construct(
        private readonly ZoneCursorStore $zoneCursorStore,
        private readonly ActiveTaskStore $activeTaskStore,
    ) {}

    /**
     * @param  array<string, mixed>  $cfg
     */
    public function cleanupTerminalActiveTasks(array $cfg): void
    {
        $retentionDays = max(1, (int) ($cfg['active_task_retention_days'] ?? 60));
        $batchLimit = max(1, (int) ($cfg['active_task_cleanup_batch'] ?? 500));
        $threshold = SchedulerRuntimeHelper::nowUtc()->subDays($retentionDays);
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
     * @return array<int, CarbonImmutable>
     */
    public function scheduleCrossings(CarbonImmutable $last, CarbonImmutable $now, string $targetTime): array
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
    public function applyCatchupPolicy(
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
    public function shouldRunIntervalTask(
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

    public function isTimeInWindow(string $nowTime, string $startTime, string $endTime): bool
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

    public function persistZoneCursor(
        int $zoneId,
        CarbonImmutable $cursorAt,
        string $catchupPolicy,
        bool $cursorPersistEnabled,
        callable $writeLog,
    ): void {
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
        $writeLog($taskName, 'cursor', [
            'zone_id' => $zoneId,
            'last_check' => SchedulerRuntimeHelper::toIso($cursorAt),
            'cursor_at' => SchedulerRuntimeHelper::toIso($cursorAt),
            'catchup_policy' => $catchupPolicy,
        ]);
    }
}
