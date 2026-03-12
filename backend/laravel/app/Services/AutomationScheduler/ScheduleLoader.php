<?php

namespace App\Services\AutomationScheduler;

use App\Models\GrowCycle;
use App\Models\SchedulerLog;
use App\Services\EffectiveTargetsService;
use Carbon\CarbonImmutable;
use Illuminate\Support\Facades\DB;

class ScheduleLoader
{
    public function __construct(
        private readonly EffectiveTargetsService $effectiveTargetsService,
        private readonly ZoneCursorStore $zoneCursorStore,
    ) {}

    /**
     * @param  array<int, int>  $zoneFilter
     * @return array<int, int>
     */
    public function loadActiveZoneIds(array $zoneFilter): array
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
    public function loadEffectiveTargetsByZone(array $zoneIds): array
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
     * @param  array<int, string>  $taskNames
     * @return array<string, CarbonImmutable>
     */
    public function loadLastRunBatch(array $taskNames): array
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
     * @param  array<int, ScheduleItem>  $schedules
     * @return array<int, string>
     */
    public function collectIntervalTaskNames(array $schedules): array
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
     * @param  array<int, CarbonImmutable>  $zoneCursorCache
     */
    public function resolveZoneLastCheck(
        int $zoneId,
        CarbonImmutable $now,
        int $dispatchIntervalSec,
        bool $cursorPersistEnabled,
        array &$zoneCursorCache,
    ): CarbonImmutable {
        if (isset($zoneCursorCache[$zoneId])) {
            return $zoneCursorCache[$zoneId];
        }

        $default = $now->subSeconds(max(30, $dispatchIntervalSec));
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
}
