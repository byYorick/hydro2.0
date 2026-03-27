<?php

namespace App\Services\AutomationScheduler;

use App\Models\GrowCycle;
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

        $resolvedPairs = [];
        foreach ($taskNames as $taskName) {
            $pair = $this->parseSchedulerTaskName((string) $taskName);
            if ($pair === null) {
                continue;
            }

            $resolvedPairs[] = $pair;
        }

        if ($resolvedPairs === []) {
            return [];
        }

        $rows = DB::table('laravel_scheduler_active_tasks')
            ->selectRaw('zone_id, task_type, MAX(COALESCE(terminal_at, updated_at, accepted_at, created_at)) AS last_at')
            ->where(function ($query) use ($resolvedPairs): void {
                foreach ($resolvedPairs as $index => $pair) {
                    $method = $index === 0 ? 'where' : 'orWhere';
                    $query->{$method}(function ($pairQuery) use ($pair): void {
                        $pairQuery
                            ->where('zone_id', $pair['zone_id'])
                            ->where('task_type', $pair['task_type']);
                    });
                }
            })
            ->whereIn('status', ['completed', 'failed', 'timeout', 'cancelled', 'expired'])
            ->groupBy('zone_id', 'task_type')
            ->get();

        $result = [];
        foreach ($rows as $row) {
            $zoneId = (int) ($row->zone_id ?? 0);
            $taskType = strtolower(trim((string) ($row->task_type ?? '')));
            if ($zoneId <= 0 || $taskType === '') {
                continue;
            }

            $taskName = SchedulerRuntimeHelper::scheduleTaskLogName($zoneId, $taskType);
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
     * @return array{zone_id:int, task_type:string}|null
     */
    private function parseSchedulerTaskName(string $taskName): ?array
    {
        if (preg_match('/^laravel_scheduler_task_([a-z0-9_]+)_zone_(\d+)$/', trim($taskName), $matches) !== 1) {
            return null;
        }

        $taskType = strtolower(trim((string) ($matches[1] ?? '')));
        $zoneId = (int) ($matches[2] ?? 0);
        if ($zoneId <= 0 || $taskType === '') {
            return null;
        }

        return [
            'zone_id' => $zoneId,
            'task_type' => $taskType,
        ];
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
