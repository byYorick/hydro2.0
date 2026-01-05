<?php

namespace Database\Seeders;

use App\Models\Sensor;
use App\Models\TelemetryLast;
use App\Models\TelemetrySample;
use App\Models\Zone;
use Carbon\Carbon;
use Illuminate\Database\Seeder;
use Illuminate\Support\Facades\Artisan;

class TelemetrySeeder extends Seeder
{
    public function run(): void
    {
        $zones = Zone::with('nodes')->get();

        if ($zones->isEmpty()) {
            $this->command->warn('Нет зон для заполнения телеметрией. Сначала запустите DemoDataSeeder.');

            return;
        }

        $this->command->info('Заполнение телеметрии для '.$zones->count().' зон...');

        foreach ($zones as $zone) {
            $nodes = $zone->nodes;

            if ($nodes->isEmpty()) {
                continue;
            }

            $this->command->info("Генерация телеметрии для зоны: {$zone->name}...");

            foreach ($nodes as $node) {
                $channels = $node->channels;

                foreach ($channels as $channel) {
                    if ($channel->type !== 'sensor') {
                        continue;
                    }

                    $metricType = strtoupper($channel->metric ?? 'PH'); // Преобразуем в верхний регистр
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

                    // Генерируем данные для миниграфиков:
                    // 1. Последние 24 часа - каждые 30 минут
                    // 2. Последние 7 дней - каждые 6 часов
                    // 3. Последние 30 дней - каждые 24 часа
                    $interval24hMinutes = 30;
                    $interval7dMinutes = 360;
                    $interval30dHours = 24;

                    $samples = [];

                    // 1. Последние 24 часа - данные для миниграфиков
                    $this->command->info('  - Генерация данных за последние 24 часа (каждые 30 минут)...');
                    $startTime24h = Carbon::now()->subDay();
                    $samples24h = (int) (24 * 60 / $interval24hMinutes);
                    for ($i = 0; $i < $samples24h; $i++) {
                        $ts = $startTime24h->copy()->addMinutes($i * $interval24hMinutes);
                        $value = $this->generateValue($baseValue, $variation, $i, $samples24h);

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

                        if (count($samples) >= 500) {
                            TelemetrySample::insert($samples);
                            $samples = [];
                        }
                    }

                    // 2. Последние 7 дней - каждые 6 часов
                    $this->command->info('  - Генерация данных за последние 7 дней (каждые 6 часов)...');
                    $startTime7d = Carbon::now()->subDays(7);
                    $samples7d = (int) (7 * 24 * 60 / $interval7dMinutes);
                    for ($i = 0; $i < $samples7d; $i++) {
                        $ts = $startTime7d->copy()->addMinutes($i * $interval7dMinutes);
                        // Пропускаем, если уже есть данные за последние 24 часа
                        if ($ts->gte($startTime24h)) {
                            continue;
                        }

                        $value = $this->generateValue($baseValue, $variation, $i, $samples7d);

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

                        if (count($samples) >= 500) {
                            TelemetrySample::insert($samples);
                            $samples = [];
                        }
                    }

                    // 3. Последние 30 дней - каждый день (для длительных периодов)
                    $this->command->info('  - Генерация данных за последние 30 дней (каждый день)...');
                    $startTime30d = Carbon::now()->subDays(30);
                    $samples30d = (int) (30 * 24 / $interval30dHours);
                    for ($i = 0; $i < $samples30d; $i++) {
                        $ts = $startTime30d->copy()->addHours($i * $interval30dHours);
                        // Пропускаем, если уже есть более детальные данные
                        if ($ts->gte($startTime7d)) {
                            continue;
                        }

                        $value = $this->generateValue($baseValue, $variation, $i, $samples30d);

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

        $this->command->info('Телеметрия заполнена успешно!');
        $this->command->info("- Всего samples: {$totalSamples}");
        $this->command->info("- Всего last values: {$totalLast}");

        // Агрегируем данные для быстрого отображения на графиках
        $this->command->info('Запуск агрегации данных...');
        try {
            Artisan::call('telemetry:aggregate', [
                '--from' => Carbon::now()->subDays(7)->toDateTimeString(),
                '--to' => Carbon::now()->toDateTimeString(),
            ]);
            $this->command->info('Агрегация завершена!');
        } catch (\Exception $e) {
            $this->command->warn('Ошибка при агрегации данных: '.$e->getMessage());
            $this->command->info('Вы можете запустить агрегацию вручную: php artisan telemetry:aggregate');
        }
    }

    /**
     * Генерация значения с реалистичными колебаниями для графиков
     */
    private function generateValue(float $baseValue, float $variation, int $index, int $total): float
    {
        // Используем несколько синусоид для создания реалистичных паттернов
        $t = $index / max($total, 1);

        // Основной тренд (медленные изменения)
        $trend = sin($t * 2 * M_PI) * ($variation * 0.3);

        // Средние колебания (дневные циклы)
        $daily = sin($t * 2 * M_PI * 7) * ($variation * 0.4);

        // Быстрые колебания (случайный шум)
        $noise = (rand(-100, 100) / 1000) * ($variation * 0.3);

        $value = $baseValue + $trend + $daily + $noise;

        // Ограничиваем значение разумными пределами
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
