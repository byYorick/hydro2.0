<?php

namespace Database\Seeders;

use Illuminate\Database\Seeder;
use App\Models\Zone;
use App\Models\DeviceNode;
use App\Models\TelemetrySample;
use App\Models\TelemetryLast;
use Carbon\Carbon;

class TelemetrySeeder extends Seeder
{
    public function run(): void
    {
        $zones = Zone::with('nodes')->get();
        
        if ($zones->isEmpty()) {
            $this->command->warn('Нет зон для заполнения телеметрией. Сначала запустите DemoDataSeeder.');
            return;
        }

        $this->command->info('Заполнение телеметрии для ' . $zones->count() . ' зон...');

        foreach ($zones as $zone) {
            $nodes = $zone->nodes;
            
            if ($nodes->isEmpty()) {
                continue;
            }

            // Генерируем телеметрию за последние 7 дней
            $days = 7;
            $samplesPerDay = 144; // Каждые 10 минут
            $totalSamples = $days * $samplesPerDay;
            
            $this->command->info("Генерация телеметрии для зоны: {$zone->name}...");

            foreach ($nodes as $node) {
                $channels = $node->channels;
                
                foreach ($channels as $channel) {
                    if ($channel->type !== 'sensor') {
                        continue;
                    }

                    $metricType = $channel->metric;
                    $baseValue = $this->getBaseValueForMetric($metricType);
                    $variation = $this->getVariationForMetric($metricType);

                    // Генерируем исторические данные
                    $samples = [];
                    $startTime = Carbon::now()->subDays($days);
                    
                    for ($i = 0; $i < $totalSamples; $i++) {
                        $ts = $startTime->copy()->addMinutes($i * 10);
                        
                        // Генерируем значение с небольшими колебаниями
                        $value = $baseValue + (sin($i / 20) * $variation) + (rand(-100, 100) / 1000 * $variation);
                        $value = max($baseValue - $variation, min($baseValue + $variation, $value));
                        
                        $samples[] = [
                            'zone_id' => $zone->id,
                            'node_id' => $node->id,
                            'channel' => $channel->channel,
                            'metric_type' => $metricType,
                            'value' => round($value, 2),
                            'ts' => $ts,
                            'created_at' => $ts,
                        ];

                        // Batch insert каждые 100 записей
                        if (count($samples) >= 100) {
                            TelemetrySample::insert($samples);
                            $samples = [];
                        }
                    }

                    // Вставка оставшихся записей
                    if (!empty($samples)) {
                        TelemetrySample::insert($samples);
                    }

                    // Обновляем telemetry_last с последним значением
                    $lastSample = TelemetrySample::where('zone_id', $zone->id)
                        ->where('node_id', $node->id)
                        ->where('metric_type', $metricType)
                        ->orderBy('ts', 'desc')
                        ->first();

                    if ($lastSample) {
                        TelemetryLast::updateOrCreate(
                            [
                                'zone_id' => $zone->id,
                                'metric_type' => $metricType,
                            ],
                            [
                                'node_id' => $node->id,
                                'channel' => $channel->channel,
                                'value' => $lastSample->value,
                                'updated_at' => $lastSample->ts,
                            ]
                        );
                    }
                }
            }
        }

        $totalSamples = TelemetrySample::count();
        $totalLast = TelemetryLast::count();
        
        $this->command->info("Телеметрия заполнена успешно!");
        $this->command->info("- Всего samples: {$totalSamples}");
        $this->command->info("- Всего last values: {$totalLast}");
    }

    private function getBaseValueForMetric(string $metric): float
    {
        return match (strtolower($metric)) {
            'ph', 'ph_value' => 5.8,
            'ec', 'ec_value' => 1.5,
            'temperature', 'temp_air' => 22.0,
            'humidity', 'humidity_air' => 60.0,
            default => 0.0,
        };
    }

    private function getVariationForMetric(string $metric): float
    {
        return match (strtolower($metric)) {
            'ph', 'ph_value' => 0.3,
            'ec', 'ec_value' => 0.2,
            'temperature', 'temp_air' => 3.0,
            'humidity', 'humidity_air' => 10.0,
            default => 1.0,
        };
    }
}

