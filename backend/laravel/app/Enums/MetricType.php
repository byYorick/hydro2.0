<?php

namespace App\Enums;

enum MetricType: string
{
    case PH = 'ph';
    case EC = 'ec';
    case TEMP_AIR = 'temp_air';
    case TEMP_WATER = 'temp_water';
    case HUMIDITY = 'humidity';
    case CO2 = 'co2';
    case LUX = 'lux';
    case WATER_LEVEL = 'water_level';
    case FLOW_RATE = 'flow_rate';
    case PUMP_CURRENT = 'pump_current';

    /**
     * Получить все значения enum.
     */
    public static function values(): array
    {
        return array_column(self::cases(), 'value');
    }

    /**
     * Проверить, является ли значение валидным типом метрики.
     */
    public static function isValid(string $value): bool
    {
        return in_array(strtolower(trim($value)), self::values(), true);
    }

    /**
     * Нормализовать значение метрики (lowercase, trim).
     */
    public static function normalize(string $value): ?string
    {
        $normalized = strtolower(trim($value));
        return self::isValid($normalized) ? $normalized : null;
    }
}

