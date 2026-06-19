<?php

namespace App\Services\AutomationScheduler;

use InvalidArgumentException;

final class ScheduleItem
{
    public readonly int $zoneId;

    public readonly string $taskType;

    public readonly ?string $time;

    public readonly ?string $startTime;

    public readonly ?string $endTime;

    public readonly int $intervalSec;

    /**
     * @var array<int, int> ISO weekday 1=Mon … 7=Sun; empty = every day
     */
    public readonly array $daysOfWeek;

    public readonly ?string $runAt;

    /**
     * @var array<string, mixed>
     */
    public readonly array $payload;

    public readonly string $scheduleKey;

    public readonly ?int $manualScheduleId;

    /**
     * @param  array<string, mixed>  $payload
     * @param  array<int, int>  $daysOfWeek
     */
    public function __construct(
        int $zoneId,
        string $taskType,
        ?string $time = null,
        ?string $startTime = null,
        ?string $endTime = null,
        int $intervalSec = 0,
        array $payload = [],
        ?int $manualScheduleId = null,
        array $daysOfWeek = [],
        ?string $runAt = null,
    ) {
        if ($zoneId <= 0) {
            throw new InvalidArgumentException('ScheduleItem zoneId must be positive integer.');
        }

        $normalizedTaskType = strtolower(trim($taskType));
        if ($normalizedTaskType === '') {
            throw new InvalidArgumentException('ScheduleItem taskType must not be empty.');
        }

        if ($intervalSec < 0) {
            throw new InvalidArgumentException('ScheduleItem intervalSec must not be negative.');
        }

        $this->zoneId = $zoneId;
        $this->taskType = $normalizedTaskType;
        $this->time = $this->normalizeTimeValue($time);
        $this->startTime = $this->normalizeTimeValue($startTime);
        $this->endTime = $this->normalizeTimeValue($endTime);
        $this->intervalSec = $intervalSec;
        $this->payload = $payload;
        $this->daysOfWeek = ScheduleSpecHelper::normalizeDaysOfWeek($daysOfWeek);
        $this->runAt = $this->normalizeRunAtValue($runAt);
        $this->manualScheduleId = $manualScheduleId !== null && $manualScheduleId > 0 ? $manualScheduleId : null;
        $this->scheduleKey = $this->manualScheduleId !== null
            ? self::makeManualScheduleKey(
                manualScheduleId: $this->manualScheduleId,
                zoneId: $this->zoneId,
                taskType: $this->taskType,
                time: $this->time,
                startTime: $this->startTime,
                endTime: $this->endTime,
                intervalSec: $this->intervalSec,
                daysOfWeek: $this->daysOfWeek,
                runAt: $this->runAt,
            )
            : self::makeScheduleKey(
                zoneId: $this->zoneId,
                taskType: $this->taskType,
                time: $this->time,
                startTime: $this->startTime,
                endTime: $this->endTime,
                intervalSec: $this->intervalSec,
                daysOfWeek: $this->daysOfWeek,
                runAt: $this->runAt,
            );
    }

    /**
     * @param  array<string, mixed>  $payload
     */
    public function withPayload(array $payload): self
    {
        return new self(
            zoneId: $this->zoneId,
            taskType: $this->taskType,
            time: $this->time,
            startTime: $this->startTime,
            endTime: $this->endTime,
            intervalSec: $this->intervalSec,
            payload: $payload,
            manualScheduleId: $this->manualScheduleId,
            daysOfWeek: $this->daysOfWeek,
            runAt: $this->runAt,
        );
    }

    /**
     * @param  array<int, int>  $daysOfWeek
     */
    public static function makeManualScheduleKey(
        int $manualScheduleId,
        int $zoneId,
        string $taskType,
        ?string $time = null,
        ?string $startTime = null,
        ?string $endTime = null,
        int $intervalSec = 0,
        array $daysOfWeek = [],
        ?string $runAt = null,
    ): string {
        return sprintf(
            'zone:%d|manual:%d',
            $zoneId,
            $manualScheduleId,
        );
    }

    /**
     * @param  array<int, int>  $daysOfWeek
     */
    public static function makeScheduleKey(
        int $zoneId,
        string $taskType,
        ?string $time,
        ?string $startTime,
        ?string $endTime,
        int $intervalSec,
        array $daysOfWeek = [],
        ?string $runAt = null,
    ): string {
        $base = sprintf(
            'zone:%d|type:%s|time=%s|start=%s|end=%s|interval=%s',
            $zoneId,
            strtolower(trim($taskType)),
            self::formatScheduleKeyValue($time),
            self::formatScheduleKeyValue($startTime),
            self::formatScheduleKeyValue($endTime),
            self::formatScheduleKeyValue($intervalSec > 0 ? (string) $intervalSec : null),
        );

        return $base.self::appendScheduleKeyMetaSuffix($daysOfWeek, $runAt);
    }

    private function normalizeTimeValue(?string $value): ?string
    {
        if ($value === null) {
            return null;
        }

        $candidate = trim($value);
        if ($candidate === '') {
            return null;
        }

        if (! preg_match('/^([01]?\d|2[0-3]):([0-5]\d)(?::([0-5]\d))?$/', $candidate, $matches)) {
            throw new InvalidArgumentException('ScheduleItem time must match HH:MM or HH:MM:SS.');
        }

        $hour = (int) $matches[1];
        $minute = (int) $matches[2];
        $second = isset($matches[3]) ? (int) $matches[3] : 0;

        return sprintf('%02d:%02d:%02d', $hour, $minute, $second);
    }

    private function normalizeRunAtValue(?string $value): ?string
    {
        if ($value === null) {
            return null;
        }

        $parsed = ScheduleSpecHelper::parseRunAt($value);

        return $parsed !== null ? SchedulerRuntimeHelper::toIso($parsed) : null;
    }

    /**
     * @param  array<int, int>  $daysOfWeek
     */
    private static function appendScheduleKeyMetaSuffix(array $daysOfWeek, ?string $runAt): string
    {
        $suffix = '';
        $normalizedDays = ScheduleSpecHelper::normalizeDaysOfWeek($daysOfWeek);
        if ($normalizedDays !== []) {
            $suffix .= '|days='.implode(',', $normalizedDays);
        }

        if ($runAt !== null && trim($runAt) !== '') {
            $suffix .= '|run_at='.trim($runAt);
        }

        return $suffix;
    }

    private static function formatScheduleKeyValue(?string $value): string
    {
        if ($value === null) {
            return 'None';
        }

        return trim($value) !== '' ? $value : 'None';
    }
}

