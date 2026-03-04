<?php

namespace App\Services\AutomationScheduler;

use Carbon\CarbonImmutable;

final class LightingScheduleParser
{
    /**
     * @param  array<string, mixed>  $lightingConfig
     * @return array<int, ScheduleItem>
     */
    public function parse(
        int $zoneId,
        array $lightingConfig,
        mixed $lightingScheduleSpec,
        CarbonImmutable $nowUtc,
    ): array {
        $intervalSec = ScheduleSpecHelper::safePositiveInt(
            $lightingConfig['interval_sec'] ?? ($lightingConfig['every_sec'] ?? ($lightingConfig['interval'] ?? null)),
        );

        $window = $this->parseWindow($lightingConfig, $lightingScheduleSpec, $nowUtc);
        if ($window !== null) {
            return [
                new ScheduleItem(
                    zoneId: $zoneId,
                    taskType: 'lighting',
                    startTime: $window['start_time'],
                    endTime: $window['end_time'],
                    intervalSec: $intervalSec,
                ),
            ];
        }

        $source = $lightingScheduleSpec ?? $lightingConfig;
        $result = [];
        foreach (ScheduleSpecHelper::extractTimeSpecs($source) as $timeSpec) {
            $result[] = new ScheduleItem(
                zoneId: $zoneId,
                taskType: 'lighting',
                time: $timeSpec,
            );
        }

        if ($intervalSec > 0) {
            $result[] = new ScheduleItem(
                zoneId: $zoneId,
                taskType: 'lighting',
                intervalSec: $intervalSec,
            );
        }

        return $result;
    }

    /**
     * @param  array<string, mixed>  $lightingConfig
     * @return array{start_time: string, end_time: string}|null
     */
    private function parseWindow(array $lightingConfig, mixed $lightingScheduleSpec, CarbonImmutable $nowUtc): ?array
    {
        $photoperiodHours = $lightingConfig['photoperiod_hours'] ?? null;
        $startFromConfig = is_string($lightingConfig['start_time'] ?? null)
            ? ScheduleSpecHelper::parseTimeSpec((string) $lightingConfig['start_time'])
            : null;
        if ($photoperiodHours !== null && $startFromConfig !== null && is_numeric($photoperiodHours)) {
            $startDt = CarbonImmutable::createFromFormat(
                'Y-m-d H:i:s',
                $nowUtc->toDateString().' '.$startFromConfig,
                'UTC',
            );
            $endDt = $startDt->addSeconds((int) round((float) $photoperiodHours * 3600));

            return [
                'start_time' => $startFromConfig,
                'end_time' => $endDt->format('H:i:s'),
            ];
        }

        if (! is_string($lightingScheduleSpec) || ! str_contains($lightingScheduleSpec, '-')) {
            return null;
        }

        [$rawStart, $rawEnd] = array_map('trim', explode('-', $lightingScheduleSpec, 2));
        $start = ScheduleSpecHelper::parseTimeSpec($rawStart);
        $end = ScheduleSpecHelper::parseTimeSpec($rawEnd);
        if ($start === null || $end === null) {
            return null;
        }

        return [
            'start_time' => $start,
            'end_time' => $end,
        ];
    }
}
