<?php

namespace Database\Seeders;

use App\Models\ParameterPrediction;
use App\Models\Zone;
use App\Models\ZoneModelParams;
use App\Models\ZoneSimulation;
use Illuminate\Database\Seeder;
use Illuminate\Support\Facades\DB;

/**
 * Расширенный сидер для AI, прогнозов и симуляций
 */
class ExtendedAIPredictionsSeeder extends Seeder
{
    public function run(): void
    {
        $this->command->info('=== Создание расширенных AI данных ===');

        $zones = Zone::all();
        if ($zones->isEmpty()) {
            $this->command->warn('Зоны не найдены.');
            return;
        }

        $predictionsCreated = 0;
        $simulationsCreated = 0;
        $modelParamsCreated = 0;

        foreach ($zones as $zone) {
            $predictionsCreated += $this->seedPredictionsForZone($zone);
            $simulationsCreated += $this->seedSimulationsForZone($zone);
            $modelParamsCreated += $this->seedModelParamsForZone($zone);
        }

        $this->command->info("Создано прогнозов: {$predictionsCreated}");
        $this->command->info("Создано симуляций: {$simulationsCreated}");
        $this->command->info("Создано параметров моделей: {$modelParamsCreated}");
        $this->command->info("Всего прогнозов: " . ParameterPrediction::count());
        $this->command->info("Всего симуляций: " . ZoneSimulation::count());
    }

    private function seedPredictionsForZone(Zone $zone): int
    {
        $created = 0;
        $metricTypes = ['ph', 'ec', 'temperature', 'humidity'];

        // Создаем прогнозы за последние 7 дней
        for ($daysAgo = 7; $daysAgo >= 0; $daysAgo--) {
            $predictedAt = now()->subDays($daysAgo)->subHours(rand(0, 23));

            foreach ($metricTypes as $metricType) {
                // Получаем базовое значение из пресета или используем дефолтное
                $baseValue = $this->getBaseValue($metricType, $zone);
                
                // Генерируем прогнозируемое значение с небольшим отклонением
                $predictedValue = $baseValue + (rand(-20, 20) / 100);
                
                // Ограничиваем значения разумными пределами
                $predictedValue = match ($metricType) {
                    'ph' => max(0, min(14, $predictedValue)),
                    'ec' => max(0, min(5, $predictedValue)),
                    'temperature' => max(10, min(35, $predictedValue)),
                    'humidity' => max(30, min(90, $predictedValue)),
                    default => $predictedValue,
                };

                ParameterPrediction::create([
                    'zone_id' => $zone->id,
                    'metric_type' => $metricType,
                    'predicted_value' => $predictedValue,
                    'confidence' => rand(75, 98) / 100,
                    'horizon_minutes' => [60, 120, 240, 480][rand(0, 3)],
                    'predicted_at' => $predictedAt,
                ]);

                $created++;
            }
        }

        return $created;
    }

    private function seedSimulationsForZone(Zone $zone): int
    {
        $created = 0;

        // Создаем несколько симуляций для каждой зоны
        $simulationCount = match ($zone->status) {
            'RUNNING' => rand(2, 5),
            'PAUSED' => rand(1, 2),
            'STOPPED' => rand(0, 1),
            default => 1,
        };

        for ($i = 0; $i < $simulationCount; $i++) {
            $scenario = [
                'days' => rand(7, 30),
                'ph_target' => rand(58, 65) / 10,
                'ec_target' => rand(15, 25) / 10,
                'temperature_target' => rand(20, 25),
                'humidity_target' => rand(55, 70),
            ];

            $results = [
                'predicted_ph' => $scenario['ph_target'] + (rand(-10, 10) / 100),
                'predicted_ec' => $scenario['ec_target'] + (rand(-10, 10) / 10),
                'predicted_temperature' => $scenario['temperature_target'] + (rand(-2, 2)),
                'predicted_humidity' => $scenario['humidity_target'] + (rand(-5, 5)),
                'predicted_yield' => rand(80, 120),
                'predicted_growth_rate' => rand(90, 110) / 100,
            ];

            $statuses = ['completed', 'running', 'failed'];
            $status = $statuses[rand(0, count($statuses) - 1)];

            ZoneSimulation::create([
                'zone_id' => $zone->id,
                'scenario' => $scenario,
                'results' => $results,
                'duration_hours' => $scenario['days'] * 24,
                'step_minutes' => 60,
                'status' => $status,
                'created_at' => now()->subDays(rand(1, 30)),
                'updated_at' => $status === 'completed' ? now()->subDays(rand(1, 5)) : now(),
            ]);

            $created++;
        }

        return $created;
    }

    private function seedModelParamsForZone(Zone $zone): int
    {
        $created = 0;

        $modelTypes = [
            'growth_prediction',
            'ph_control',
            'ec_control',
            'climate_control',
        ];

        foreach ($modelTypes as $modelType) {
            $exists = DB::table('zone_model_params')
                ->where('zone_id', $zone->id)
                ->where('model_type', $modelType)
                ->exists();

            if ($exists) {
                continue;
            }

            $params = match ($modelType) {
                'growth_prediction' => [
                    'growth_rate' => rand(80, 120) / 100,
                    'efficiency' => rand(70, 95) / 100,
                    'yield_factor' => rand(90, 110) / 100,
                ],
                'ph_control' => [
                    'kp' => rand(10, 30) / 10,
                    'ki' => rand(5, 15) / 10,
                    'kd' => rand(1, 5) / 10,
                    'target_ph' => rand(58, 65) / 10,
                ],
                'ec_control' => [
                    'kp' => rand(10, 30) / 10,
                    'ki' => rand(5, 15) / 10,
                    'kd' => rand(1, 5) / 10,
                    'target_ec' => rand(15, 25) / 10,
                ],
                'climate_control' => [
                    'temp_kp' => rand(10, 30) / 10,
                    'humidity_kp' => rand(10, 30) / 10,
                    'target_temp' => rand(20, 25),
                    'target_humidity' => rand(55, 70),
                ],
                default => [],
            };

            DB::table('zone_model_params')->insert([
                'zone_id' => $zone->id,
                'model_type' => $modelType,
                'params' => json_encode($params),
                'calibrated_at' => now()->subDays(rand(1, 30)),
                'created_at' => now()->subDays(rand(1, 30)),
                'updated_at' => now()->subDays(rand(1, 30)),
            ]);

            $created++;
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

