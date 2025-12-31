<?php

namespace App\Services;

use Illuminate\Support\Facades\Cache;

/**
 * Сервис фильтрации телеметрии для Zone Event Ledger.
 *
 * Определяет, нужно ли записывать событие телеметрии в ledger.
 * Записывает только значимые изменения (превышающие порог) и не чаще минимального интервала.
 */
class TelemetryLedgerFilter
{
    /**
     * Пороги значимых изменений для разных метрик.
     *
     * Значение будет записано в ledger только если разница с предыдущим
     * записанным значением превышает порог.
     */
    private const THRESHOLDS = [
        'PH' => 0.1,           // Изменение pH на 0.1 считается значимым
        'EC' => 0.2,           // Изменение EC на 0.2 mS/cm
        'TEMPERATURE' => 1.0,  // Изменение температуры на 1°C
        'HUMIDITY' => 2.0,     // Изменение влажности на 2%
        'CO2' => 50,           // Изменение CO2 на 50 ppm
        'LIGHT_INTENSITY' => 100, // Изменение освещенности на 100 lux
        // Для других метрик используем значение по умолчанию
    ];

    /**
     * Минимальный интервал между записями для каждой метрики (в секундах).
     *
     * Даже при значимом изменении событие не будет записано,
     * если прошло меньше времени, чем указано в интервале.
     */
    private const MIN_INTERVAL_SECONDS = 60; // 1 минута

    /**
     * Значение по умолчанию для порога, если метрика не указана в THRESHOLDS.
     */
    private const DEFAULT_THRESHOLD = 1.0;

    /**
     * Проверяет, нужно ли записывать событие телеметрии в ledger.
     *
     * @param  int  $zoneId  ID зоны
     * @param  string  $metricType  Тип метрики (PH, EC, TEMPERATURE, и т.д.)
     * @param  float  $value  Текущее значение метрики
     * @return bool true, если событие нужно записать в ledger
     */
    public function shouldRecord(int $zoneId, string $metricType, float $value): bool
    {
        $cacheKey = "telemetry_last_recorded:zone_{$zoneId}:{$metricType}";

        // Получаем последнее записанное значение из кеша
        $lastRecorded = Cache::get($cacheKey);

        if ($lastRecorded === null) {
            // Первое значение для этой метрики в этой зоне - записываем
            $this->updateCache($cacheKey, $value);

            return true;
        }

        $lastValue = $lastRecorded['value'];
        $lastTimestamp = $lastRecorded['timestamp'];

        // Проверяем интервал времени
        $timeSinceLastRecord = time() - $lastTimestamp;
        if ($timeSinceLastRecord < self::MIN_INTERVAL_SECONDS) {
            // Слишком часто - не записываем
            return false;
        }

        // Проверяем значимость изменения
        $threshold = self::THRESHOLDS[$metricType] ?? self::DEFAULT_THRESHOLD;
        $change = abs($value - $lastValue);

        if ($change < $threshold) {
            // Изменение незначимо - не записываем
            return false;
        }

        // Значимое изменение - записываем и обновляем кеш
        $this->updateCache($cacheKey, $value);

        return true;
    }

    /**
     * Обновляет кеш последнего записанного значения.
     *
     * @param  string  $cacheKey  Ключ кеша
     * @param  float  $value  Значение для сохранения
     */
    private function updateCache(string $cacheKey, float $value): void
    {
        Cache::put($cacheKey, [
            'value' => $value,
            'timestamp' => time(),
        ], now()->addHours(24));
    }
}
