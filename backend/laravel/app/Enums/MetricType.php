<?php

namespace App\Enums;

enum MetricType: string
{
    case PH = 'PH';
    case EC = 'EC';
    case TEMPERATURE = 'TEMPERATURE';
    case HUMIDITY = 'HUMIDITY';
    case CO2 = 'CO2';
    case LIGHT_INTENSITY = 'LIGHT_INTENSITY';
    case WATER_LEVEL = 'WATER_LEVEL';
    case FLOW_RATE = 'FLOW_RATE';
    case PUMP_CURRENT = 'PUMP_CURRENT';

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
        return in_array(strtoupper(trim($value)), self::values(), true);
    }

    /**
     * Нормализовать значение метрики (lowercase, trim).
     */
    public static function normalize(string $value): ?string
    {
        $normalized = strtoupper(trim($value));

        return self::isValid($normalized) ? $normalized : null;
    }
}
