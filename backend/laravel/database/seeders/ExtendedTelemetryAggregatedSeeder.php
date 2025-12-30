<?php

namespace Database\Seeders;

use App\Models\DeviceNode;
use App\Models\Zone;
use Illuminate\Database\Seeder;
use Illuminate\Support\Facades\DB;

/**
 * Сидер для агрегированной телеметрии
 */
class ExtendedTelemetryAggregatedSeeder extends Seeder
{
    public function run(): void
    {
        $this->command->info('=== Создание агрегированной телеметрии ===');

        $zones = Zone::all();
        if ($zones->isEmpty()) {
            $this->command->warn('Зоны не найдены.');
            return;
        }

        $agg1mCreated = $this->seedAggregated1m($zones);
        $agg1hCreated = $this->seedAggregated1h($zones);
        $dailyCreated = $this->seedDaily($zones);

        $this->command->info("Создано агрегации 1m: " . number_format($agg1mCreated));
        $this->command->info("Создано агрегации 1h: " . number_format($agg1hCreated));
        $this->command->info("Создано дневной агрегации: " . number_format($dailyCreated));
    }

    private function seedAggregated1m($zones): int
    {
        $created = 0;
        $metricTypes = ['ph', 'ec', 'temperature', 'humidity'];
        $batch = [];
        $batchSize = 500;
        $uniqueBy = ['zone_id', 'node_id', 'channel', 'metric_type', 'ts'];
        $updateColumns = ['value_avg', 'value_min', 'value_max', 'value_median', 'sample_count', 'created_at'];

        // Создаем данные за последние 7 дней, по 1 минуте
        foreach ($zones as $zone) {
            $nodes = DeviceNode::where('zone_id', $zone->id)->get();
            if ($nodes->isEmpty()) {
                continue;
            }

            $node = $nodes->first();
            $startTime = now()->subDays(7)->startOfDay();

            for ($day = 0; $day < 7; $day++) {
                for ($hour = 0; $hour < 24; $hour++) {
                    $ts = $startTime->copy()->addDays($day)->addHours($hour);

                    foreach ($metricTypes as $metricType) {
                        $baseValue = $this->getBaseValue($metricType, $zone);
                        $value = $baseValue + (rand(-10, 10) / 100);

                        $batch[] = [
                            'zone_id' => $zone->id,
                            'node_id' => $node->id,
                            'channel' => $metricType,
                            'metric_type' => $metricType,
                            'ts' => $ts,
                            'value_avg' => $value,
                            'value_min' => $value - 0.1,
                            'value_max' => $value + 0.1,
                            'value_median' => $value,
                            'sample_count' => rand(10, 12),
                            'created_at' => $ts,
                        ];

                        $created++;

                        if (count($batch) >= $batchSize) {
                            DB::table('telemetry_agg_1m')->upsert($batch, $uniqueBy, $updateColumns);
                            $batch = [];
                        }
                    }
                }
            }
        }

        if (!empty($batch)) {
            DB::table('telemetry_agg_1m')->upsert($batch, $uniqueBy, $updateColumns);
        }

        return $created;
    }

    private function seedAggregated1h($zones): int
    {
        $created = 0;
        $metricTypes = ['ph', 'ec', 'temperature', 'humidity'];
        $batch = [];
        $batchSize = 500;
        $uniqueBy = ['zone_id', 'node_id', 'channel', 'metric_type', 'ts'];
        $updateColumns = ['value_avg', 'value_min', 'value_max', 'value_median', 'sample_count', 'created_at'];

        // Создаем данные за последние 30 дней, по 1 часу
        foreach ($zones as $zone) {
            $nodes = DeviceNode::where('zone_id', $zone->id)->get();
            if ($nodes->isEmpty()) {
                continue;
            }

            $node = $nodes->first();
            $startTime = now()->subDays(30)->startOfDay();

            for ($day = 0; $day < 30; $day++) {
                for ($hour = 0; $hour < 24; $hour++) {
                    $ts = $startTime->copy()->addDays($day)->addHours($hour);

                    foreach ($metricTypes as $metricType) {
                        $baseValue = $this->getBaseValue($metricType, $zone);
                        $value = $baseValue + (rand(-20, 20) / 100);

                        $batch[] = [
                            'zone_id' => $zone->id,
                            'node_id' => $node->id,
                            'channel' => $metricType,
                            'metric_type' => $metricType,
                            'ts' => $ts,
                            'value_avg' => $value,
                            'value_min' => $value - 0.2,
                            'value_max' => $value + 0.2,
                            'value_median' => $value,
                            'sample_count' => rand(50, 60),
                            'created_at' => $ts,
                        ];

                        $created++;

                        if (count($batch) >= $batchSize) {
                            DB::table('telemetry_agg_1h')->upsert($batch, $uniqueBy, $updateColumns);
                            $batch = [];
                        }
                    }
                }
            }
        }

        if (!empty($batch)) {
            DB::table('telemetry_agg_1h')->upsert($batch, $uniqueBy, $updateColumns);
        }

        return $created;
    }

    private function seedDaily($zones): int
    {
        $created = 0;
        $metricTypes = ['ph', 'ec', 'temperature', 'humidity'];
        $batch = [];
        $batchSize = 500;
        $uniqueBy = ['zone_id', 'node_id', 'channel', 'metric_type', 'date'];
        $updateColumns = ['value_avg', 'value_min', 'value_max', 'value_median', 'sample_count', 'created_at'];

        // Создаем данные за последние 90 дней
        foreach ($zones as $zone) {
            $nodes = DeviceNode::where('zone_id', $zone->id)->get();
            if ($nodes->isEmpty()) {
                continue;
            }

            $node = $nodes->first();
            $startDate = now()->subDays(90)->startOfDay();

            for ($day = 0; $day < 90; $day++) {
                $date = $startDate->copy()->addDays($day);

                foreach ($metricTypes as $metricType) {
                    $baseValue = $this->getBaseValue($metricType, $zone);
                    $value = $baseValue + (rand(-30, 30) / 100);

                    $batch[] = [
                        'zone_id' => $zone->id,
                        'node_id' => $node->id,
                        'channel' => $metricType,
                        'metric_type' => $metricType,
                        'date' => $date->toDateString(),
                        'value_avg' => $value,
                        'value_min' => $value - 0.5,
                        'value_max' => $value + 0.5,
                        'value_median' => $value,
                        'sample_count' => rand(200, 300),
                        'created_at' => $date,
                    ];

                    $created++;

                    if (count($batch) >= $batchSize) {
                        DB::table('telemetry_daily')->upsert($batch, $uniqueBy, $updateColumns);
                        $batch = [];
                    }
                }
            }
        }

        if (!empty($batch)) {
            DB::table('telemetry_daily')->upsert($batch, $uniqueBy, $updateColumns);
        }

        return $created;
    }

    private function getBaseValue(string $metricType, Zone $zone): float
    {
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

        return match ($metricType) {
            'ph' => 6.5,
            'ec' => 1.8,
            'temperature' => 22.0,
            'humidity' => 65.0,
            default => 0,
        };
    }
}
