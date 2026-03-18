<?php

namespace Database\Seeders\Support;

class CanonicalRecipePhaseSupport
{
    public static function inferSystemType(?string $irrigationMode): ?string
    {
        return match (strtoupper((string) $irrigationMode)) {
            'RECIRC' => 'nft',
            'SUBSTRATE' => 'drip',
            default => null,
        };
    }

    public static function buildDayNight(
        ?float $dayTemp,
        ?float $nightTemp,
        ?float $dayHumidity,
        ?float $nightHumidity,
        ?float $dayPh,
        ?float $nightPh,
        ?float $dayEc,
        ?float $nightEc,
        ?string $lightingStartTime,
        ?float $dayHours
    ): array {
        return [
            'ph' => [
                'day' => $dayPh,
                'night' => $nightPh,
            ],
            'ec' => [
                'day' => $dayEc,
                'night' => $nightEc,
            ],
            'temperature' => [
                'day' => $dayTemp,
                'night' => $nightTemp,
            ],
            'humidity' => [
                'day' => $dayHumidity,
                'night' => $nightHumidity,
            ],
            'lighting' => [
                'day_start_time' => $lightingStartTime,
                'day_hours' => $dayHours,
            ],
        ];
    }

    public static function mergeExtensions(?array $extensions, ?string $irrigationMode, ?array $dayNight): ?array
    {
        $payload = is_array($extensions) ? $extensions : [];

        if ($dayNight !== null) {
            $payload['day_night'] = $dayNight;
        }

        $systemType = self::inferSystemType($irrigationMode);
        if ($systemType !== null) {
            $payload['subsystems']['irrigation']['targets']['system_type'] = $systemType;
        }

        return empty($payload) ? null : $payload;
    }
}
