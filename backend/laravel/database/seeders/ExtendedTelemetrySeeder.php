<?php

namespace Database\Seeders;

use App\Models\DeviceNode;
use App\Models\NodeChannel;
use App\Models\Sensor;
use App\Models\TelemetryLast;
use App\Models\TelemetrySample;
use App\Models\Zone;
use Illuminate\Database\Seeder;

/**
 * Расширенный сидер для телеметрии
 * Создает исторические данные и последние значения для всех зон
 */
class ExtendedTelemetrySeeder extends Seeder
{
    public function run(): void
    {
        $this->command->info('=== Создание расширенной телеметрии ===');

        $zones = Zone::all();
        if ($zones->isEmpty()) {
            $this->command->warn('Зоны не найдены.');
            return;
        }

        $samplesCreated = 0;
        $lastUpdated = 0;

        foreach ($zones as $zone) {
            $sensors = $this->getOrCreateZoneSensors($zone);
            if ($sensors->isEmpty()) {
                continue;
            }

            // Создаем исторические данные
            $samplesCreated += $this->seedHistoricalTelemetry($zone, $sensors);

            // Обновляем последние значения
            $lastUpdated += $this->seedTelemetryLast($zone, $sensors);
        }

        $this->command->info("Создано samples: " . number_format($samplesCreated));
        $this->command->info("Обновлено last значений: {$lastUpdated}");
        $this->command->info("Всего samples: " . number_format(TelemetrySample::count()));
        $this->command->info("Всего last значений: " . TelemetryLast::count());
    }

    private function seedHistoricalTelemetry(Zone $zone, $sensors): int
    {
        $samplesCreated = 0;
        $intervalMinutes = 5; // Интервал между измерениями
        $batch = [];
        $batchSize = 500;

        $metricTypes = ['ph', 'ec', 'temperature', 'humidity'];
        
        // Определяем количество дней в зависимости от статуса зоны
        $status = strtolower((string) $zone->status);
        $daysBack = match ($status) {
            'running', 'online' => 7,
            'paused', 'warning' => 3,
            'stopped', 'critical' => 1,
            default => 1,
        };

        $now = now();
        $startTime = $now->copy()->subDays($daysBack)->startOfDay();

        // Группируем сенсоры по метрикам
        $sensorsByMetric = [];
        foreach ($sensors as $sensor) {
            $metric = $this->metricFromSensorType($sensor->type);
            if ($metric && in_array($metric, $metricTypes, true)) {
                $sensorsByMetric[$metric][] = $sensor;
            }
        }

        // Генерируем данные с интервалом
        $currentTime = $startTime->copy();
        while ($currentTime->lt($now)) {
            foreach ($metricTypes as $metricType) {
                if (empty($sensorsByMetric[$metricType])) {
                    continue;
                }

                // Выбираем случайный сенсор для этой метрики
                $sensor = $sensorsByMetric[$metricType][array_rand($sensorsByMetric[$metricType])];

                // Генерируем реалистичное значение с небольшими колебаниями
                $baseValue = $this->getBaseValue($metricType, $zone);
                $value = $this->generateRealisticValue($baseValue, $metricType, $currentTime);

                $batch[] = [
                    'zone_id' => $zone->id,
                    'sensor_id' => $sensor->id,
                    'cycle_id' => $zone->activeGrowCycle?->id,
                    'value' => $value,
                    'ts' => $currentTime,
                    'quality' => 'GOOD',
                    'metadata' => json_encode([
                        'metric' => $metricType,
                        'source' => 'seeder',
                    ], JSON_UNESCAPED_UNICODE),
                ];

                $samplesCreated++;

                if (count($batch) >= $batchSize) {
                    \DB::table('telemetry_samples')->insert($batch);
                    $batch = [];
                }
            }

            $currentTime->addMinutes($intervalMinutes);
        }

        if (!empty($batch)) {
            \DB::table('telemetry_samples')->insert($batch);
        }

        return $samplesCreated;
    }

    private function seedTelemetryLast(Zone $zone, $sensors): int
    {
        $updated = 0;
        $metricTypes = ['ph', 'ec', 'temperature', 'humidity'];

        foreach ($metricTypes as $metricType) {
            $sensor = $sensors->first(function ($sensor) use ($metricType) {
                return $this->metricFromSensorType($sensor->type) === $metricType;
            });

            if (!$sensor) {
                continue;
            }

            // Получаем последнее значение из samples или генерируем новое
            $lastSample = TelemetrySample::where('sensor_id', $sensor->id)
                ->orderBy('ts', 'desc')
                ->first();

            $value = $lastSample
                ? $lastSample->value
                : $this->getBaseValue($metricType, $zone);

            TelemetryLast::updateOrCreate(
                [
                    'sensor_id' => $sensor->id,
                ],
                [
                    'last_value' => $value,
                    'last_ts' => $lastSample?->ts ?? now(),
                    'last_quality' => 'GOOD',
                ]
            );

            $updated++;
        }

        return $updated;
    }

    private function getBaseValue(string $metricType, Zone $zone): float
    {
        // Получаем базовые значения из пресета зоны, если он есть
        $preset = $zone->preset;
        
        if ($preset) {
            return match ($metricType) {
                'ph' => ($preset->ph_optimal_range['min'] ?? 6.0) + (($preset->ph_optimal_range['max'] ?? 6.5) - ($preset->ph_optimal_range['min'] ?? 6.0)) / 2,
                'ec' => ($preset->ec_range['min'] ?? 1.5) + (($preset->ec_range['max'] ?? 2.0) - ($preset->ec_range['min'] ?? 1.5)) / 2,
                'temperature' => ($preset->climate_ranges['temp_day']['min'] ?? 20) + (($preset->climate_ranges['temp_day']['max'] ?? 24) - ($preset->climate_ranges['temp_day']['min'] ?? 20)) / 2,
                'humidity' => ($preset->climate_ranges['humidity_day']['min'] ?? 60) + (($preset->climate_ranges['humidity_day']['max'] ?? 70) - ($preset->climate_ranges['humidity_day']['min'] ?? 60)) / 2,
                default => 0,
            };
        }

        // Значения по умолчанию
        return match ($metricType) {
            'ph' => 6.5,
            'ec' => 1.8,
            'temperature' => 22.0,
            'humidity' => 65.0,
            default => 0,
        };
    }

    private function generateRealisticValue(float $baseValue, string $metricType, \DateTime $time): float
    {
        // Добавляем реалистичные колебания
        $hour = (int)$time->format('H');
        $variation = match ($metricType) {
            'ph' => 0.3, // ±0.3 pH
            'ec' => 0.2, // ±0.2 mS/cm
            'temperature' => 2.0, // ±2°C
            'humidity' => 5.0, // ±5%
            default => 1.0,
        };

        // Синусоидальные колебания в течение дня
        $dayCycle = sin(($hour - 6) * M_PI / 12) * ($variation / 2);
        $randomVariation = (rand(-100, 100) / 100) * ($variation / 2);

        $value = $baseValue + $dayCycle + $randomVariation;

        // Ограничиваем значения разумными пределами
        return match ($metricType) {
            'ph' => max(0, min(14, $value)),
            'ec' => max(0, min(5, $value)),
            'temperature' => max(10, min(35, $value)),
            'humidity' => max(30, min(90, $value)),
            default => $value,
        };
    }

    private function getOrCreateZoneSensors(Zone $zone)
    {
        $sensors = Sensor::query()
            ->where('zone_id', $zone->id)
            ->where('is_active', true)
            ->get();

        if ($sensors->isNotEmpty()) {
            return $sensors;
        }

        $nodes = DeviceNode::where('zone_id', $zone->id)->get();
        if ($nodes->isEmpty()) {
            return collect();
        }

        $channels = NodeChannel::whereIn('node_id', $nodes->pluck('id')->toArray())
            ->where('type', 'sensor')
            ->get();

        foreach ($channels as $channel) {
            $sensorType = $this->sensorTypeFromMetric($channel->metric);
            if (! $sensorType) {
                continue;
            }

            Sensor::firstOrCreate(
                [
                    'greenhouse_id' => $zone->greenhouse_id,
                    'zone_id' => $zone->id,
                    'node_id' => $channel->node_id,
                    'type' => $sensorType,
                    'label' => $this->buildSensorLabel($channel, $sensorType),
                ],
                [
                    'scope' => 'inside',
                    'unit' => $channel->unit,
                    'specs' => [
                        'channel' => $channel->channel,
                        'metric' => $channel->metric,
                    ],
                    'is_active' => true,
                ]
            );
        }

        return Sensor::query()
            ->where('zone_id', $zone->id)
            ->where('is_active', true)
            ->get();
    }

    private function sensorTypeFromMetric(?string $metric): ?string
    {
        $metric = strtoupper((string) $metric);

        return match (true) {
            $metric === 'PH' => 'PH',
            $metric === 'EC' => 'EC',
            str_contains($metric, 'TEMP') => 'TEMPERATURE',
            str_contains($metric, 'HUM') => 'HUMIDITY',
            default => null,
        };
    }

    private function metricFromSensorType(?string $type): ?string
    {
        return match (strtoupper((string) $type)) {
            'PH' => 'ph',
            'EC' => 'ec',
            'TEMPERATURE' => 'temperature',
            'HUMIDITY' => 'humidity',
            default => null,
        };
    }

    private function buildSensorLabel(NodeChannel $channel, string $sensorType): string
    {
        $base = $channel->channel ?: strtolower($sensorType);
        $base = str_replace('_', ' ', strtolower($base));
        $base = trim($base) ?: strtolower($sensorType);

        return ucfirst($base);
    }
}
