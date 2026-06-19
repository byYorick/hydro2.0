<?php

namespace App\Services\AutomationScheduler;

use App\Models\Zone;
use App\Models\ZoneManualSchedule;

class ManualScheduleItemBuilder
{
    /**
     * @return array<int, ScheduleItem>
     */
    public function buildForZone(int $zoneId): array
    {
        if ($zoneId <= 0) {
            return [];
        }

        $rows = ZoneManualSchedule::query()
            ->where('zone_id', $zoneId)
            ->where('enabled', true)
            ->orderBy('id')
            ->get();

        $items = [];
        foreach ($rows as $row) {
            $item = $this->toScheduleItem($row);
            if ($item !== null) {
                $items[] = $item;
            }
        }

        return $items;
    }

    /**
     * @param  array<int, int>  $zoneIds
     * @return array<int, array<int, ScheduleItem>>
     */
    public function buildForZones(array $zoneIds): array
    {
        $normalizedZoneIds = array_values(array_filter(array_map(
            static fn ($value): int => (int) $value,
            $zoneIds,
        ), static fn (int $value): bool => $value > 0));

        if ($normalizedZoneIds === []) {
            return [];
        }

        $rows = ZoneManualSchedule::query()
            ->whereIn('zone_id', $normalizedZoneIds)
            ->where('enabled', true)
            ->orderBy('zone_id')
            ->orderBy('id')
            ->get();

        $result = [];
        foreach ($rows as $row) {
            $zoneId = (int) $row->zone_id;
            $item = $this->toScheduleItem($row);
            if ($item === null) {
                continue;
            }

            $result[$zoneId] ??= [];
            $result[$zoneId][] = $item;
        }

        return $result;
    }

    public function toScheduleItem(ZoneManualSchedule $row): ?ScheduleItem
    {
        $zoneId = (int) $row->zone_id;
        $taskType = strtolower(trim((string) $row->task_type));
        $kind = strtolower(trim((string) $row->schedule_kind));
        if ($zoneId <= 0 || $taskType === '' || $kind === '') {
            return null;
        }

        if (! $row->enabled) {
            return null;
        }

        $zone = Zone::query()->find($zoneId);
        if (
            $zone instanceof Zone
            && $zone->automation_runtime === 'ae3'
            && ! in_array($taskType, ManualScheduleService::AE3_EXECUTABLE_TASK_TYPES, true)
        ) {
            return null;
        }

        if ($kind === 'once' && $row->last_dispatched_at !== null) {
            return null;
        }

        $payload = is_array($row->payload) ? $row->payload : [];
        $payload['origin'] = 'manual';
        $payload['manual_schedule_id'] = (int) $row->id;
        if (is_string($row->label) && trim($row->label) !== '') {
            $payload['label'] = trim($row->label);
        }

        if ($taskType === 'irrigation') {
            $durationSec = ScheduleSpecHelper::safePositiveInt($payload['duration_sec'] ?? null);
            if ($durationSec > 0) {
                $payload['duration_sec'] = $durationSec;
            }
        }

        $daysOfWeek = ScheduleSpecHelper::normalizeDaysOfWeek($row->days_of_week);

        return match ($kind) {
            'time' => $this->buildTimeItem($row, $zoneId, $taskType, $payload, $daysOfWeek),
            'interval' => $this->buildIntervalItem($row, $zoneId, $taskType, $payload, $daysOfWeek),
            'window' => $this->buildWindowItem($row, $zoneId, $taskType, $payload, $daysOfWeek),
            'once' => $this->buildOnceItem($row, $zoneId, $taskType, $payload),
            default => null,
        };
    }

    /**
     * @param  array<string, mixed>  $payload
     * @param  array<int, int>  $daysOfWeek
     */
    private function buildTimeItem(
        ZoneManualSchedule $row,
        int $zoneId,
        string $taskType,
        array $payload,
        array $daysOfWeek,
    ): ?ScheduleItem {
        $time = $this->normalizeStoredTime($row->time_at);
        if ($time === null) {
            return null;
        }

        return new ScheduleItem(
            zoneId: $zoneId,
            taskType: $taskType,
            time: $time,
            payload: $payload,
            manualScheduleId: (int) $row->id,
            daysOfWeek: $daysOfWeek,
        );
    }

    /**
     * @param  array<string, mixed>  $payload
     * @param  array<int, int>  $daysOfWeek
     */
    private function buildIntervalItem(
        ZoneManualSchedule $row,
        int $zoneId,
        string $taskType,
        array $payload,
        array $daysOfWeek,
    ): ?ScheduleItem {
        $intervalSec = ScheduleSpecHelper::safePositiveInt($row->interval_sec);
        if ($intervalSec < 60) {
            return null;
        }

        return new ScheduleItem(
            zoneId: $zoneId,
            taskType: $taskType,
            intervalSec: $intervalSec,
            payload: $payload,
            manualScheduleId: (int) $row->id,
            daysOfWeek: $daysOfWeek,
        );
    }

    /**
     * @param  array<string, mixed>  $payload
     * @param  array<int, int>  $daysOfWeek
     */
    private function buildWindowItem(
        ZoneManualSchedule $row,
        int $zoneId,
        string $taskType,
        array $payload,
        array $daysOfWeek,
    ): ?ScheduleItem {
        $startTime = $this->normalizeStoredTime($row->window_start);
        $endTime = $this->normalizeStoredTime($row->window_end);
        if ($startTime === null || $endTime === null) {
            return null;
        }

        return new ScheduleItem(
            zoneId: $zoneId,
            taskType: $taskType,
            startTime: $startTime,
            endTime: $endTime,
            payload: $payload,
            manualScheduleId: (int) $row->id,
            daysOfWeek: $daysOfWeek,
        );
    }

    /**
     * @param  array<string, mixed>  $payload
     */
    private function buildOnceItem(
        ZoneManualSchedule $row,
        int $zoneId,
        string $taskType,
        array $payload,
    ): ?ScheduleItem {
        if ($row->run_at === null) {
            return null;
        }

        $runAt = ScheduleSpecHelper::parseRunAt($row->run_at->toIso8601String());
        if ($runAt === null) {
            return null;
        }

        return new ScheduleItem(
            zoneId: $zoneId,
            taskType: $taskType,
            payload: $payload,
            manualScheduleId: (int) $row->id,
            runAt: SchedulerRuntimeHelper::toIso($runAt),
        );
    }

    private function normalizeStoredTime(mixed $value): ?string
    {
        if ($value === null) {
            return null;
        }

        $candidate = trim((string) $value);
        if ($candidate === '') {
            return null;
        }

        if (str_contains($candidate, ' ')) {
            $parts = explode(' ', $candidate);
            $candidate = (string) end($parts);
        }

        return ScheduleSpecHelper::parseTimeSpec($candidate);
    }
}
