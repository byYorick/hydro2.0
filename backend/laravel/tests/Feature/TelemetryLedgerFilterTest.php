<?php

namespace Tests\Feature;

use App\Models\Zone;
use App\Models\Greenhouse;
use App\Models\DeviceNode;
use App\Services\TelemetryLedgerFilter;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Illuminate\Support\Facades\Cache;
use Tests\TestCase;

class TelemetryLedgerFilterTest extends TestCase
{
    use RefreshDatabase;

    private TelemetryLedgerFilter $filter;
    private Zone $zone;

    protected function setUp(): void
    {
        parent::setUp();
        
        $this->filter = app(TelemetryLedgerFilter::class);
        
        $greenhouse = Greenhouse::factory()->create();
        $this->zone = Zone::factory()->create(['greenhouse_id' => $greenhouse->id]);
        
        // Очищаем кеш перед каждым тестом
        Cache::flush();
    }

    public function test_first_value_is_always_recorded(): void
    {
        // Первое значение для метрики всегда записывается
        $result = $this->filter->shouldRecord($this->zone->id, 'pH', 6.5);
        $this->assertTrue($result, 'Первое значение должно быть записано');
    }

    public function test_significant_change_is_recorded(): void
    {
        // Первое значение
        $this->filter->shouldRecord($this->zone->id, 'pH', 6.5);
        
        // Симуляция времени (минуем интервал)
        $this->advanceTimeForMetric('pH', 61);
        
        // Значимое изменение (pH изменился на 0.15, порог 0.1)
        $result = $this->filter->shouldRecord($this->zone->id, 'pH', 6.65);
        $this->assertTrue($result, 'Значимое изменение должно быть записано');
    }

    public function test_insignificant_change_is_not_recorded(): void
    {
        // Первое значение
        $this->filter->shouldRecord($this->zone->id, 'pH', 6.5);
        
        // Симуляция времени (минуем интервал)
        $this->advanceTimeForMetric('pH', 61);
        
        // Незначимое изменение (pH изменился на 0.05, порог 0.1)
        $result = $this->filter->shouldRecord($this->zone->id, 'pH', 6.55);
        $this->assertFalse($result, 'Незначимое изменение не должно быть записано');
    }

    public function test_too_frequent_updates_are_not_recorded(): void
    {
        // Первое значение
        $this->filter->shouldRecord($this->zone->id, 'pH', 6.5);
        
        // Симуляция времени (прошло только 30 секунд)
        $this->advanceTimeForMetric('pH', 30);
        
        // Даже при значимом изменении не записываем (слишком часто)
        $result = $this->filter->shouldRecord($this->zone->id, 'pH', 7.0);
        $this->assertFalse($result, 'Слишком частые обновления не должны записываться');
    }

    public function test_different_metrics_have_different_thresholds(): void
    {
        // pH: порог 0.1
        $this->filter->shouldRecord($this->zone->id, 'pH', 6.5);
        $this->advanceTimeForMetric('pH', 61);
        
        // Изменение 0.15 - значимо для pH
        $result = $this->filter->shouldRecord($this->zone->id, 'pH', 6.65);
        $this->assertTrue($result, 'Изменение pH на 0.15 должно быть значимым');
        
        // EC: порог 0.2
        $this->filter->shouldRecord($this->zone->id, 'EC', 1.5);
        $this->advanceTimeForMetric('EC', 61);
        
        // Изменение 0.15 - НЕ значимо для EC (порог 0.2)
        $result = $this->filter->shouldRecord($this->zone->id, 'EC', 1.65);
        $this->assertFalse($result, 'Изменение EC на 0.15 не должно быть значимым');
        
        // Для следующей проверки нужно снова симулировать время
        $this->advanceTimeForMetric('EC', 61);
        
        // Изменение 0.25 от последнего записанного значения (1.65) - значимо для EC
        $result = $this->filter->shouldRecord($this->zone->id, 'EC', 1.90);
        $this->assertTrue($result, 'Изменение EC на 0.25 должно быть значимым');
    }

    public function test_different_zones_have_independent_filtering(): void
    {
        $zone2 = Zone::factory()->create(['greenhouse_id' => $this->zone->greenhouse_id]);
        
        // Записываем значение для зоны 1
        $this->filter->shouldRecord($this->zone->id, 'pH', 6.5);
        
        // Для зоны 2 первое значение тоже записывается
        $result = $this->filter->shouldRecord($zone2->id, 'pH', 6.5);
        $this->assertTrue($result, 'Первое значение для другой зоны должно записываться');
    }

    public function test_negative_change_is_handled_correctly(): void
    {
        // Первое значение
        $this->filter->shouldRecord($this->zone->id, 'pH', 6.5);
        $this->advanceTimeForMetric('pH', 61);
        
        // Отрицательное изменение (уменьшение)
        $result = $this->filter->shouldRecord($this->zone->id, 'pH', 6.3);
        $this->assertTrue($result, 'Отрицательное изменение на 0.2 должно быть значимым');
    }

    public function test_unknown_metric_uses_default_threshold(): void
    {
        // Неизвестная метрика должна использовать DEFAULT_THRESHOLD = 1.0
        $this->filter->shouldRecord($this->zone->id, 'UNKNOWN_METRIC', 10.0);
        $this->advanceTimeForMetric('UNKNOWN_METRIC', 61);
        
        // Изменение на 0.5 - незначимо (порог 1.0)
        $result = $this->filter->shouldRecord($this->zone->id, 'UNKNOWN_METRIC', 10.5);
        $this->assertFalse($result, 'Изменение на 0.5 не должно быть значимым для неизвестной метрики');
        
        // Для следующей проверки нужно снова симулировать время
        $this->advanceTimeForMetric('UNKNOWN_METRIC', 61);
        
        // Изменение на 1.1 от последнего записанного значения (10.5) = 11.6 - значимо
        $result = $this->filter->shouldRecord($this->zone->id, 'UNKNOWN_METRIC', 11.6);
        $this->assertTrue($result, 'Изменение на 1.1 должно быть значимым для неизвестной метрики');
    }

    /**
     * Вспомогательный метод для симуляции прохождения времени.
     * Обновляет timestamp в кеше для указанной метрики, чтобы симулировать прошедшее время.
     */
    private function advanceTimeForMetric(string $metricType, int $seconds): void
    {
        $cacheKey = "telemetry_last_recorded:zone_{$this->zone->id}:{$metricType}";
        $lastValue = Cache::get($cacheKey);
        
        if ($lastValue) {
            // Обновляем timestamp на прошлое время (имитируем, что прошло $seconds секунд)
            Cache::put($cacheKey, [
                'value' => $lastValue['value'],
                'timestamp' => time() - $seconds,
            ], now()->addHours(24));
        }
    }
}

