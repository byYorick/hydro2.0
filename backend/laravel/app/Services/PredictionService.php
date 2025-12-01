<?php

namespace App\Services;

use App\Models\ParameterPrediction;
use App\Models\TelemetrySample;
use App\Models\Zone;
use Carbon\Carbon;
use Illuminate\Support\Facades\Log;

class PredictionService
{
    /**
     * Прогнозирование параметра для зоны
     *
     * @param  string  $metricType  ph, ec, temp_air, humidity_air
     * @param  int  $horizonMinutes  горизонт прогноза в минутах (по умолчанию 60)
     */
    public function predict(Zone $zone, string $metricType, int $horizonMinutes = 60): ?ParameterPrediction
    {
        try {
            // Получаем последние данные за 2 часа для анализа тренда
            $from = Carbon::now()->subHours(2);

            $samples = TelemetrySample::query()
                ->where('zone_id', $zone->id)
                ->where('metric_type', $metricType)
                ->where('ts', '>=', $from)
                ->orderBy('ts', 'asc')
                ->get(['ts', 'value'])
                ->filter(fn ($s) => $s->value !== null);

            if ($samples->count() < 3) {
                Log::warning('Not enough samples for prediction', [
                    'zone_id' => $zone->id,
                    'metric_type' => $metricType,
                    'samples_count' => $samples->count(),
                ]);

                return null;
            }

            // Простая линейная регрессия
            $prediction = $this->linearRegression($samples, $horizonMinutes);

            if (! $prediction) {
                return null;
            }

            // Сохраняем прогноз
            $predictedAt = Carbon::now()->addMinutes($horizonMinutes);

            $model = ParameterPrediction::create([
                'zone_id' => $zone->id,
                'metric_type' => $metricType,
                'predicted_value' => $prediction['value'],
                'confidence' => $prediction['confidence'],
                'horizon_minutes' => $horizonMinutes,
                'predicted_at' => $predictedAt,
            ]);

            Log::info('Prediction generated', [
                'zone_id' => $zone->id,
                'metric_type' => $metricType,
                'predicted_value' => $prediction['value'],
                'confidence' => $prediction['confidence'],
                'horizon_minutes' => $horizonMinutes,
            ]);

            return $model;
        } catch (\Exception $e) {
            Log::error('Failed to generate prediction', [
                'zone_id' => $zone->id,
                'metric_type' => $metricType,
                'error' => $e->getMessage(),
            ]);

            return null;
        }
    }

    /**
     * Простая линейная регрессия для прогнозирования
     *
     * @param  \Illuminate\Support\Collection  $samples
     * @return array|null ['value' => float, 'confidence' => float]
     */
    private function linearRegression($samples, int $horizonMinutes): ?array
    {
        $n = $samples->count();
        if ($n < 3) {
            return null;
        }

        // Преобразуем время в минуты от первого образца
        $firstTime = $samples->first()->ts;
        $x = [];
        $y = [];

        foreach ($samples as $sample) {
            $minutes = $firstTime->diffInMinutes($sample->ts);
            $x[] = $minutes;
            $y[] = (float) $sample->value;
        }

        // Вычисляем средние значения
        $xMean = array_sum($x) / $n;
        $yMean = array_sum($y) / $n;

        // Вычисляем коэффициенты регрессии
        $numerator = 0;
        $denominator = 0;

        for ($i = 0; $i < $n; $i++) {
            $numerator += ($x[$i] - $xMean) * ($y[$i] - $yMean);
            $denominator += pow($x[$i] - $xMean, 2);
        }

        if ($denominator == 0) {
            // Нет тренда, возвращаем последнее значение
            return [
                'value' => $y[$n - 1],
                'confidence' => 0.5,
            ];
        }

        $slope = $numerator / $denominator;
        $intercept = $yMean - $slope * $xMean;

        // Прогнозируем значение через horizon_minutes
        $futureX = $x[$n - 1] + $horizonMinutes;
        $predictedValue = $intercept + $slope * $futureX;

        // Вычисляем confidence на основе R² (упрощенный)
        $ssRes = 0;
        $ssTot = 0;
        for ($i = 0; $i < $n; $i++) {
            $predicted = $intercept + $slope * $x[$i];
            $ssRes += pow($y[$i] - $predicted, 2);
            $ssTot += pow($y[$i] - $yMean, 2);
        }

        $rSquared = $ssTot > 0 ? 1 - ($ssRes / $ssTot) : 0;
        $confidence = max(0.0, min(1.0, $rSquared)); // Ограничиваем 0-1

        return [
            'value' => $predictedValue,
            'confidence' => $confidence,
        ];
    }

    /**
     * Получить последний прогноз для зоны и метрики
     */
    public function getLatestPrediction(Zone $zone, string $metricType): ?ParameterPrediction
    {
        return ParameterPrediction::query()
            ->where('zone_id', $zone->id)
            ->where('metric_type', $metricType)
            ->orderByDesc('predicted_at')
            ->orderByDesc('created_at')
            ->orderByDesc('id')
            ->first();
    }

    /**
     * Генерация прогнозов для всех активных зон
     *
     * @param  array  $metricTypes  массив типов метрик для прогнозирования
     * @return int количество созданных прогнозов
     */
    public function generatePredictionsForActiveZones(array $metricTypes = ['ph', 'ec']): int
    {
        $zones = Zone::query()
            ->whereIn('status', ['online', 'warning'])
            ->get();

        $count = 0;
        foreach ($zones as $zone) {
            foreach ($metricTypes as $metricType) {
                $prediction = $this->predict($zone, $metricType, 60);
                if ($prediction) {
                    $count++;
                }
            }
        }

        return $count;
    }
}
