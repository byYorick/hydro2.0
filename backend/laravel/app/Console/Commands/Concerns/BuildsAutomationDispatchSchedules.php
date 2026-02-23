<?php

namespace App\Console\Commands\Concerns;

use App\Models\SchedulerLog;
use Carbon\CarbonImmutable;

trait BuildsAutomationDispatchSchedules
{
    /**
     * @param  array<string, mixed>  $targets
     * @return array<int, array<string, mixed>>
     */
    private function buildSchedulesForZone(int $zoneId, array $targets): array
    {
        $schedules = [];

        $irrigation = is_array($targets['irrigation'] ?? null) ? $targets['irrigation'] : [];
        $irrigationSchedule = $targets['irrigation_schedule'] ?? ($irrigation['schedule'] ?? null);
        if ($this->isTaskScheduleEnabled('irrigation', $targets, $irrigation)) {
            foreach ($this->buildGenericTaskSchedules($zoneId, 'irrigation', $irrigation, $irrigationSchedule, $targets) as $schedule) {
                $schedules[] = $schedule;
            }
        }

        $lighting = is_array($targets['lighting'] ?? null) ? $targets['lighting'] : [];
        $lightingIntervalSec = $this->safePositiveInt(
            $lighting['interval_sec'] ?? ($lighting['every_sec'] ?? ($lighting['interval'] ?? null))
        );
        if ($this->isTaskScheduleEnabled('lighting', $targets, $lighting)) {
            $photoperiodHours = $lighting['photoperiod_hours'] ?? null;
            $startTime = is_string($lighting['start_time'] ?? null)
                ? $this->parseTimeSpec((string) $lighting['start_time'])
                : null;
            if ($photoperiodHours !== null && $startTime !== null && is_numeric($photoperiodHours)) {
                $startDt = CarbonImmutable::createFromFormat('Y-m-d H:i:s', $this->nowUtc()->toDateString().' '.$startTime, 'UTC');
                $endDt = $startDt->addSeconds((int) round((float) $photoperiodHours * 3600));
                $scheduleItem = [
                    'zone_id' => $zoneId,
                    'type' => 'lighting',
                    'start_time' => $startTime,
                    'end_time' => $endDt->format('H:i:s'),
                    'targets' => $targets,
                    'config' => $lighting,
                ];
                if ($lightingIntervalSec > 0) {
                    $scheduleItem['interval_sec'] = $lightingIntervalSec;
                }
                $schedules[] = $scheduleItem;
            } else {
                $lightingSchedule = $targets['lighting_schedule'] ?? null;
                if (is_string($lightingSchedule) && str_contains($lightingSchedule, '-')) {
                    [$rawStart, $rawEnd] = array_map('trim', explode('-', $lightingSchedule, 2));
                    $start = $this->parseTimeSpec($rawStart);
                    $end = $this->parseTimeSpec($rawEnd);
                    if ($start !== null && $end !== null) {
                        $scheduleItem = [
                            'zone_id' => $zoneId,
                            'type' => 'lighting',
                            'start_time' => $start,
                            'end_time' => $end,
                            'targets' => $targets,
                            'config' => $lighting,
                        ];
                        if ($lightingIntervalSec > 0) {
                            $scheduleItem['interval_sec'] = $lightingIntervalSec;
                        }
                        $schedules[] = $scheduleItem;
                    }
                } else {
                    foreach ($this->buildGenericTaskSchedules($zoneId, 'lighting', $lighting, $lightingSchedule, $targets) as $schedule) {
                        $schedules[] = $schedule;
                    }
                }
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
            foreach ($this->buildGenericTaskSchedules($zoneId, (string) $taskType, (array) $config, $source, $targets) as $schedule) {
                $schedules[] = $schedule;
            }
        }

        return $schedules;
    }

    /**
     * @param  array<string, mixed>  $config
     * @param  array<string, mixed>  $targets
     * @return array<int, array<string, mixed>>
     */
    private function buildGenericTaskSchedules(
        int $zoneId,
        string $taskType,
        array $config,
        mixed $scheduleSpec,
        array $targets,
    ): array {
        $schedules = [];

        foreach ($this->extractTimeSpecs($scheduleSpec) as $timeSpec) {
            $schedules[] = [
                'zone_id' => $zoneId,
                'type' => $taskType,
                'time' => $timeSpec,
                'targets' => $targets,
                'config' => $config,
            ];
        }

        $intervalSec = $this->safePositiveInt(
            $config['interval_sec'] ?? ($config['every_sec'] ?? ($config['interval'] ?? null))
        );
        if ($intervalSec > 0) {
            $schedules[] = [
                'zone_id' => $zoneId,
                'type' => $taskType,
                'interval_sec' => $intervalSec,
                'targets' => $targets,
                'config' => $config,
            ];
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
     * @return array<int, string>
     */
    private function extractTimeSpecs(mixed $value): array
    {
        if ($value === null) {
            return [];
        }

        $rawItems = [];
        if (is_string($value)) {
            $rawItems = array_filter(array_map('trim', explode(',', $value)));
        } elseif (is_array($value)) {
            if (array_is_list($value)) {
                $rawItems = $value;
            } elseif (is_array($value['times'] ?? null)) {
                $rawItems = $value['times'];
            } elseif (is_string($value['time'] ?? null)) {
                $rawItems = [$value['time']];
            }
        }

        $result = [];
        foreach ($rawItems as $item) {
            $parsed = $this->parseTimeSpec((string) $item);
            if ($parsed !== null) {
                $result[] = $parsed;
            }
        }

        return $result;
    }

    private function parseTimeSpec(string $spec): ?string
    {
        $candidate = trim($spec);
        if ($candidate === '') {
            return null;
        }

        if (! preg_match('/^([01]?\d|2[0-3]):([0-5]\d)(?::([0-5]\d))?$/', $candidate, $matches)) {
            return null;
        }

        $hour = (int) $matches[1];
        $minute = (int) $matches[2];
        $second = isset($matches[3]) ? (int) $matches[3] : 0;

        return sprintf('%02d:%02d:%02d', $hour, $minute, $second);
    }

    private function safePositiveInt(mixed $value): int
    {
        if (! is_numeric($value)) {
            return 0;
        }
        $parsed = (int) $value;

        return $parsed > 0 ? $parsed : 0;
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

    private function shouldRunIntervalTask(string $taskName, int $intervalSec, CarbonImmutable $now): bool
    {
        if ($intervalSec <= 0) {
            return false;
        }

        $lastTerminalLog = SchedulerLog::query()
            ->where('task_name', $taskName)
            ->whereIn('status', ['completed', 'failed'])
            ->orderByDesc('created_at')
            ->orderByDesc('id')
            ->first(['created_at']);

        if (! $lastTerminalLog?->created_at) {
            return true;
        }

        $lastCompletedAt = CarbonImmutable::instance($lastTerminalLog->created_at)->utc();

        return $lastCompletedAt->addSeconds($intervalSec)->lte($now);
    }

    private function resolveZoneLastCheck(int $zoneId, CarbonImmutable $now, bool $cursorPersistEnabled): CarbonImmutable
    {
        if (isset($this->zoneCursorCache[$zoneId])) {
            return $this->zoneCursorCache[$zoneId];
        }

        $default = $now->subSeconds(max(30, (int) config('services.automation_engine.scheduler_dispatch_interval_sec', 60)));
        if (! $cursorPersistEnabled) {
            $this->zoneCursorCache[$zoneId] = $default;

            return $default;
        }

        $storedCursor = $this->zoneCursorStore->getCursorAt($zoneId);
        if ($storedCursor !== null) {
            $this->zoneCursorCache[$zoneId] = $storedCursor;

            return $storedCursor;
        }

        $this->zoneCursorCache[$zoneId] = $default;

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

    /**
     * @param  array<string, mixed>  $schedule
     */
    private function buildScheduleKey(int $zoneId, array $schedule): string
    {
        $taskType = strtolower((string) ($schedule['type'] ?? ''));
        $time = $this->formatScheduleKeyValue($schedule['time'] ?? null);
        $start = $this->formatScheduleKeyValue($schedule['start_time'] ?? null);
        $end = $this->formatScheduleKeyValue($schedule['end_time'] ?? null);
        $interval = $this->formatScheduleKeyValue($schedule['interval_sec'] ?? null);

        return sprintf(
            'zone:%d|type:%s|time=%s|start=%s|end=%s|interval=%s',
            $zoneId,
            $taskType,
            $time,
            $start,
            $end,
            $interval,
        );
    }

    private function formatScheduleKeyValue(mixed $value): string
    {
        if ($value === null) {
            return 'None';
        }

        return trim((string) $value) !== '' ? (string) $value : 'None';
    }

    private function isTimeInWindow(string $nowTime, string $startTime, string $endTime): bool
    {
        $now = $this->timeToSeconds($nowTime);
        $start = $this->timeToSeconds($startTime);
        $end = $this->timeToSeconds($endTime);
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

    private function timeToSeconds(string $timeSpec): ?int
    {
        $parsed = $this->parseTimeSpec($timeSpec);
        if ($parsed === null) {
            return null;
        }
        [$hour, $minute, $second] = array_map('intval', explode(':', $parsed));

        return ($hour * 3600) + ($minute * 60) + $second;
    }
}
