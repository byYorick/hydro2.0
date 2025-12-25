<?php

namespace Database\Seeders;

use App\Models\DeviceNode;
use App\Models\NodeChannel;
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
            $nodes = DeviceNode::where('zone_id', $zone->id)->get();
            if ($nodes->isEmpty()) {
                continue;
            }

            // Создаем исторические данные за последние 7 дней
            $samplesCreated += $this->seedHistoricalTelemetry($zone, $nodes);
            
            // Обновляем последние значения
            $lastUpdated += $this->seedTelemetryLast($zone, $nodes);
        }

        $this->command->info("Создано samples: " . number_format($samplesCreated));
        $this->command->info("Обновлено last значений: {$lastUpdated}");
        $this->command->info("Всего samples: " . number_format(TelemetrySample::count()));
        $this->command->info("Всего last значений: " . TelemetryLast::count());
    }

    private function seedHistoricalTelemetry(Zone $zone, $nodes): int
    {
        $samplesCreated = 0;
        $daysBack = 7;
        $intervalMinutes = 5; // Интервал между измерениями

        $metricTypes = ['ph', 'ec', 'temperature', 'humidity'];
        
        // Определяем количество дней в зависимости от статуса зоны
        $daysBack = match ($zone->status) {
            'RUNNING' => 7,
            'PAUSED' => 3,
            'STOPPED' => 1,
            default => 1,
        };

        $now = now();
        $startTime = $now->copy()->subDays($daysBack)->startOfDay();

        // Получаем каналы для узлов зоны
        $nodeIds = $nodes->pluck('id')->toArray();
        $channels = NodeChannel::whereIn('node_id', $nodeIds)->get();

        // Группируем каналы по метрикам
        $channelsByMetric = [];
        foreach ($channels as $channel) {
            $metric = strtolower($channel->metric);
            if (in_array($metric, $metricTypes)) {
                if (!isset($channelsByMetric[$metric])) {
                    $channelsByMetric[$metric] = [];
                }
                $channelsByMetric[$metric][] = $channel;
            }
        }

        // Генерируем данные с интервалом
        $currentTime = $startTime->copy();
        while ($currentTime->lt($now)) {
            foreach ($metricTypes as $metricType) {
                if (!isset($channelsByMetric[$metricType])) {
                    continue;
                }

                // Выбираем случайный канал для этой метрики
                $channel = $channelsByMetric[$metricType][array_rand($channelsByMetric[$metricType])];
                $node = $nodes->firstWhere('id', $channel->node_id);

                if (!$node) {
                    continue;
                }

                // Генерируем реалистичное значение с небольшими колебаниями
                $baseValue = $this->getBaseValue($metricType, $zone);
                $value = $this->generateRealisticValue($baseValue, $metricType, $currentTime);

                TelemetrySample::create([
                    'zone_id' => $zone->id,
                    'node_id' => $node->id,
                    'channel' => $channel->channel,
                    'metric_type' => $metricType,
                    'value' => $value,
                    'ts' => $currentTime,
                ]);

                $samplesCreated++;
            }

            $currentTime->addMinutes($intervalMinutes);
        }

        return $samplesCreated;
    }

    private function seedTelemetryLast(Zone $zone, $nodes): int
    {
        $updated = 0;
        $metricTypes = ['ph', 'ec', 'temperature', 'humidity'];

        $nodeIds = $nodes->pluck('id')->toArray();
        $channels = NodeChannel::whereIn('node_id', $nodeIds)->get();

        foreach ($metricTypes as $metricType) {
            // Находим канал для этой метрики
            $channel = $channels->first(function ($ch) use ($metricType) {
                return strtolower($ch->metric) === $metricType;
            });

            if (!$channel) {
                continue;
            }

            $node = $nodes->firstWhere('id', $channel->node_id);
            if (!$node) {
                continue;
            }

            // Получаем последнее значение из samples или генерируем новое
            $lastSample = TelemetrySample::where('zone_id', $zone->id)
                ->where('metric_type', $metricType)
                ->orderBy('ts', 'desc')
                ->first();

            $value = $lastSample 
                ? $lastSample->value 
                : $this->getBaseValue($metricType, $zone);

            TelemetryLast::updateOrCreate(
                [
                    'zone_id' => $zone->id,
                    'metric_type' => $metricType,
                ],
                [
                    'node_id' => $node->id,
                    'value' => $value,
                    'updated_at' => now(),
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
}

