<?php

namespace App\Services\AutomationScheduler;

use App\Models\Zone;
use Carbon\CarbonImmutable;
use Illuminate\Support\Facades\DB;

final class LightingScheduleParser
{
    /** @var array<int, string|null> Кеш timezone по zone_id на один dispatch-cycle */
    private array $timezoneCache = [];

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

        $window = $this->parseWindow($zoneId, $lightingConfig, $lightingScheduleSpec, $nowUtc);
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
    private function parseWindow(int $zoneId, array $lightingConfig, mixed $lightingScheduleSpec, CarbonImmutable $nowUtc): ?array
    {
        $photoperiodHours = $lightingConfig['photoperiod_hours'] ?? null;
        $startFromConfig = is_string($lightingConfig['start_time'] ?? null)
            ? ScheduleSpecHelper::parseTimeSpec((string) $lightingConfig['start_time'])
            : null;
        if ($photoperiodHours !== null && $startFromConfig !== null && is_numeric($photoperiodHours)) {
            // start_time хранится как локальное время теплицы (HH:MM:SS). Парсим
            // его в TZ теплицы, добавляем photoperiod и конвертируем end в UTC-
            // эквивалент. Если TZ не определён — fallback на UTC (старое
            // поведение, сохраняет backward compat).
            $tz = $this->resolveZoneTimezone($zoneId) ?? 'UTC';
            $startDt = CarbonImmutable::createFromFormat(
                'Y-m-d H:i:s',
                $nowUtc->setTimezone($tz)->toDateString().' '.$startFromConfig,
                $tz,
            );
            if ($startDt === false) {
                return null;
            }
            $endDt = $startDt->addSeconds((int) round((float) $photoperiodHours * 3600));

            return [
                'start_time' => $startFromConfig,
                // end_time отдаём в локальном времени теплицы для симметрии.
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

    private function resolveZoneTimezone(int $zoneId): ?string
    {
        if (array_key_exists($zoneId, $this->timezoneCache)) {
            return $this->timezoneCache[$zoneId];
        }

        $tz = DB::table('zones')
            ->leftJoin('greenhouses', 'zones.greenhouse_id', '=', 'greenhouses.id')
            ->where('zones.id', $zoneId)
            ->value('greenhouses.timezone');

        $normalized = is_string($tz) && trim($tz) !== '' ? trim($tz) : null;
        if ($normalized !== null) {
            try {
                new \DateTimeZone($normalized);
            } catch (\Throwable) {
                $normalized = null;
            }
        }
        $this->timezoneCache[$zoneId] = $normalized;

        return $normalized;
    }
}
