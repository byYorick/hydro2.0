<?php

namespace Database\Seeders;

use App\Models\Sensor;
use App\Models\TelemetryLast;
use App\Models\TelemetrySample;
use App\Models\Zone;
use Carbon\Carbon;
use Illuminate\Database\Seeder;
use Illuminate\Support\Facades\Artisan;

/**
 * Сидер для быстрого заполнения данных телеметрии для миниграфиков
 * Генерирует данные за последние 24 часа с интервалом 1 минута
 */
class TelemetryMiniGraphSeeder extends Seeder
{
    public function run(): void
    {
        $zones = Zone::with('nodes.channels')->get();

        if ($zones->isEmpty()) {
            $this->command->warn('Нет зон для заполнения телеметрией. Сначала запустите DemoDataSeeder.');

            return;
        }

        $this->command->info('Заполнение данных для миниграфиков...');

        foreach ($zones as $zone) {
            $nodes = $zone->nodes;

            if ($nodes->isEmpty()) {
                continue;
            }

            $this->command->info("Генерация данных для зоны: {$zone->name}...");

            foreach ($nodes as $node) {
                $channels = $node->channels;

                foreach ($channels as $channel) {
                    if ($channel->type !== 'sensor') {
                        continue;
                    }

                    $metricType = strtoupper($channel->metric ?? 'PH');
                    $sensorType = $this->sensorTypeFromMetric($metricType);
                    if (! $sensorType) {
                        continue;
                    }

                    $sensor = Sensor::firstOrCreate(
                        [
                            'greenhouse_id' => $zone->greenhouse_id,
                            'zone_id' => $zone->id,
                            'node_id' => $node->id,
                            'scope' => 'inside',
                            'type' => $sensorType,
                            'label' => $this->buildSensorLabel($channel->channel ?? null, $sensorType),
                        ],
                        [
                            'unit' => $channel->unit,
                            'specs' => [
                                'channel' => $channel->channel,
                                'metric' => $channel->metric,
                            ],
                            'is_active' => true,
                        ]
                    );
                    $baseValue = $this->getBaseValueForMetric($metricType);
                    $variation = $this->getVariationForMetric($metricType);

                    // Генерируем данные за последние 24 часа - каждую минуту
                    $samples = [];
                    $startTime = Carbon::now()->subDay();

                    $this->command->info("  - Метрика {$metricType}: генерация 1440 точек...");

                    for ($i = 0; $i < 1440; $i++) {
                        $ts = $startTime->copy()->addMinutes($i);
                        $value = $this->generateValue($baseValue, $variation, $i, 1440);

                        $samples[] = [
                            'zone_id' => $zone->id,
                            'sensor_id' => $sensor->id,
                            'value' => round($value, 2),
                            'ts' => $ts,
                            'created_at' => $ts,
                            'quality' => 'GOOD',
                            'metadata' => json_encode([
                                'metric_type' => $metricType,
                                'channel' => $channel->channel ?? 'default',
                            ], JSON_UNESCAPED_UNICODE),
                        ];

                        // Batch insert каждые 500 записей
                        if (count($samples) >= 500) {
                            TelemetrySample::insert($samples);
                            $samples = [];
                        }
                    }

                    // Вставка оставшихся записей
                    if (! empty($samples)) {
                        TelemetrySample::insert($samples);
                    }

                    // Обновляем telemetry_last с последним значением
                    $lastSample = TelemetrySample::where('zone_id', $zone->id)
                        ->where('sensor_id', $sensor->id)
                        ->orderBy('ts', 'desc')
                        ->first();

                    if ($lastSample) {
                        TelemetryLast::updateOrCreate(
                            [
                                'sensor_id' => $sensor->id,
                            ],
                            [
                                'last_value' => $lastSample->value,
                                'last_ts' => $lastSample->ts,
                                'last_quality' => $lastSample->quality ?? 'GOOD',
                            ]
                        );
                    }
                }
            }
        }

        $totalSamples = TelemetrySample::count();
        $totalLast = TelemetryLast::count();

        $this->command->info('Данные для миниграфиков заполнены успешно!');
        $this->command->info("- Всего samples: {$totalSamples}");
        $this->command->info("- Всего last values: {$totalLast}");

        // Агрегируем данные
        $this->command->info('Запуск агрегации данных...');
        try {
            Artisan::call('telemetry:aggregate', [
                '--from' => Carbon::now()->subDay()->toDateTimeString(),
                '--to' => Carbon::now()->toDateTimeString(),
            ]);
            $this->command->info('Агрегация завершена!');
        } catch (\Exception $e) {
            $this->command->warn('Ошибка при агрегации: '.$e->getMessage());
        }
    }

    /**
     * Генерация значения с реалистичными колебаниями
     */
    private function generateValue(float $baseValue, float $variation, int $index, int $total): float
    {
        $t = $index / max($total, 1);

        // Основной тренд (медленные изменения)
        $trend = sin($t * 2 * M_PI) * ($variation * 0.3);

        // Средние колебания (дневные циклы)
        $daily = sin($t * 2 * M_PI * 7) * ($variation * 0.4);

        // Быстрые колебания (случайный шум)
        $noise = (rand(-100, 100) / 1000) * ($variation * 0.3);

        $value = $baseValue + $trend + $daily + $noise;

        return max($baseValue - $variation * 1.5, min($baseValue + $variation * 1.5, $value));
    }

    private function getBaseValueForMetric(string $metric): float
    {
        return match (strtoupper($metric)) {
            'PH', 'PH_VALUE' => 5.8,
            'EC', 'EC_VALUE' => 1.5,
            'TEMPERATURE' => 22.0,
            'HUMIDITY' => 60.0,
            'WATER_LEVEL' => 50.0,
            'FLOW_RATE' => 2.0,
            default => 0.0,
        };
    }

    private function getVariationForMetric(string $metric): float
    {
        return match (strtoupper($metric)) {
            'PH', 'PH_VALUE' => 0.3,
            'EC', 'EC_VALUE' => 0.2,
            'TEMPERATURE' => 3.0,
            'HUMIDITY' => 10.0,
            'WATER_LEVEL' => 15.0,
            'FLOW_RATE' => 0.5,
            default => 1.0,
        };
    }

    private function sensorTypeFromMetric(string $metric): ?string
    {
        $metric = strtoupper($metric);

        return match ($metric) {
            'PH' => 'PH',
            'EC' => 'EC',
            'TEMPERATURE' => 'TEMPERATURE',
            'HUMIDITY' => 'HUMIDITY',
            default => null,
        };
    }

    private function buildSensorLabel(?string $channel, string $sensorType): string
    {
        $base = $channel ?: strtolower($sensorType);
        $base = str_replace('_', ' ', strtolower($base));
        $base = trim($base) ?: strtolower($sensorType);

        return ucfirst($base);
    }
}
