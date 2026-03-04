<?php

namespace App\Services\AutomationScheduler;

final class ScheduleSpecHelper
{
    /**
     * @return array<int, string>
     */
    public static function extractTimeSpecs(mixed $value): array
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
            $parsed = self::parseTimeSpec((string) $item);
            if ($parsed !== null) {
                $result[] = $parsed;
            }
        }

        return $result;
    }

    public static function parseTimeSpec(string $spec): ?string
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

    public static function safePositiveInt(mixed $value): int
    {
        if (! is_numeric($value)) {
            return 0;
        }
        $parsed = (int) $value;

        return $parsed > 0 ? $parsed : 0;
    }

    public static function timeToSeconds(string $timeSpec): ?int
    {
        $parsed = self::parseTimeSpec($timeSpec);
        if ($parsed === null) {
            return null;
        }
        [$hour, $minute, $second] = array_map('intval', explode(':', $parsed));

        return ($hour * 3600) + ($minute * 60) + $second;
    }
}
