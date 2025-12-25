<?php

namespace Database\Seeders;

use App\Models\Greenhouse;
use App\Models\Preset;
use App\Models\Zone;
use Illuminate\Database\Seeder;
use Illuminate\Support\Str;

/**
 * Расширенный сидер для теплиц и зон
 * Создает разнообразные теплицы с множеством зон в разных состояниях
 */
class ExtendedGreenhousesZonesSeeder extends Seeder
{
    public function run(): void
    {
        $this->command->info('=== Создание расширенных теплиц и зон ===');

        // Получаем пресеты
        $presets = Preset::all();
        if ($presets->isEmpty()) {
            $this->command->warn('Пресеты не найдены. Запустите PresetSeeder сначала.');
            return;
        }

        // Создаем теплицы
        $greenhouses = $this->seedGreenhouses();
        
        // Создаем зоны для каждой теплицы
        foreach ($greenhouses as $greenhouse) {
            $this->seedZonesForGreenhouse($greenhouse, $presets);
        }

        $this->command->info("Создано теплиц: " . Greenhouse::count());
        $this->command->info("Создано зон: " . Zone::count());
    }

    private function seedGreenhouses(): array
    {
        $greenhouses = [];

        $greenhouseData = [
            [
                'uid' => 'gh-main-production',
                'name' => 'Основная Производственная Теплица',
                'type' => 'indoor',
                'timezone' => 'Europe/Moscow',
                'coordinates' => ['lat' => 55.7558, 'lon' => 37.6173],
                'description' => 'Основная производственная теплица для круглогодичного выращивания',
            ],
            [
                'uid' => 'gh-research',
                'name' => 'Исследовательская Теплица',
                'type' => 'indoor',
                'timezone' => 'Europe/Moscow',
                'coordinates' => ['lat' => 55.7559, 'lon' => 37.6174],
                'description' => 'Теплица для исследований и экспериментов',
            ],
            [
                'uid' => 'gh-outdoor-seasonal',
                'name' => 'Сезонная Открытая Теплица',
                'type' => 'outdoor',
                'timezone' => 'Europe/Moscow',
                'coordinates' => ['lat' => 55.7560, 'lon' => 37.6175],
                'description' => 'Открытая теплица для сезонного выращивания',
            ],
            [
                'uid' => 'gh-training',
                'name' => 'Обучающая Теплица',
                'type' => 'indoor',
                'timezone' => 'Europe/Moscow',
                'coordinates' => ['lat' => 55.7561, 'lon' => 37.6176],
                'description' => 'Теплица для обучения персонала',
            ],
            [
                'uid' => 'gh-demo',
                'name' => 'Демонстрационная Теплица',
                'type' => 'indoor',
                'timezone' => 'Europe/Moscow',
                'coordinates' => ['lat' => 55.7562, 'lon' => 37.6177],
                'description' => 'Демонстрационная теплица для клиентов',
            ],
        ];

        foreach ($greenhouseData as $data) {
            $greenhouse = Greenhouse::firstOrCreate(
                ['uid' => $data['uid']],
                array_merge($data, [
                    'provisioning_token' => 'gh_' . Str::random(32),
                ])
            );
            $greenhouses[] = $greenhouse;
        }

        return $greenhouses;
    }

    private function seedZonesForGreenhouse(Greenhouse $greenhouse, $presets): void
    {
        $zoneConfigs = [
            // Основная производственная теплица - много зон
            'gh-main-production' => [
                ['name' => 'Зона A1 - Салат', 'status' => 'RUNNING', 'preset_index' => 0],
                ['name' => 'Зона A2 - Салат', 'status' => 'RUNNING', 'preset_index' => 0],
                ['name' => 'Зона B1 - Базилик', 'status' => 'RUNNING', 'preset_index' => 4],
                ['name' => 'Зона B2 - Базилик', 'status' => 'PAUSED', 'preset_index' => 4],
                ['name' => 'Зона C1 - Томаты', 'status' => 'RUNNING', 'preset_index' => 2],
                ['name' => 'Зона C2 - Томаты', 'status' => 'RUNNING', 'preset_index' => 2],
                ['name' => 'Зона D1 - Огурцы', 'status' => 'RUNNING', 'preset_index' => 2],
                ['name' => 'Зона E1 - Руккола', 'status' => 'RUNNING', 'preset_index' => 1],
                ['name' => 'Зона E2 - Руккола', 'status' => 'STOPPED', 'preset_index' => 1],
                ['name' => 'Зона F1 - Микрозелень', 'status' => 'RUNNING', 'preset_index' => 3],
            ],
            // Исследовательская теплица - меньше зон
            'gh-research' => [
                ['name' => 'Исследовательская Зона 1', 'status' => 'RUNNING', 'preset_index' => 0],
                ['name' => 'Исследовательская Зона 2', 'status' => 'RUNNING', 'preset_index' => 1],
                ['name' => 'Исследовательская Зона 3', 'status' => 'PAUSED', 'preset_index' => 2],
            ],
            // Сезонная теплица
            'gh-outdoor-seasonal' => [
                ['name' => 'Сезонная Зона 1', 'status' => 'RUNNING', 'preset_index' => 2],
                ['name' => 'Сезонная Зона 2', 'status' => 'STOPPED', 'preset_index' => 2],
            ],
            // Обучающая теплица
            'gh-training' => [
                ['name' => 'Обучающая Зона 1', 'status' => 'RUNNING', 'preset_index' => 0],
                ['name' => 'Обучающая Зона 2', 'status' => 'RUNNING', 'preset_index' => 3],
            ],
            // Демонстрационная теплица
            'gh-demo' => [
                ['name' => 'Демо Зона 1', 'status' => 'RUNNING', 'preset_index' => 0],
                ['name' => 'Демо Зона 2', 'status' => 'RUNNING', 'preset_index' => 4],
            ],
        ];

        $configs = $zoneConfigs[$greenhouse->uid] ?? [];

        foreach ($configs as $config) {
            $preset = $presets->get($config['preset_index'] % $presets->count());
            
            Zone::firstOrCreate(
                [
                    'greenhouse_id' => $greenhouse->id,
                    'name' => $config['name'],
                ],
                [
                    'uid' => 'zone-' . Str::random(16),
                    'description' => "Зона для выращивания в {$greenhouse->name}",
                    'status' => $config['status'],
                    'preset_id' => $preset->id,
                    'health_score' => $config['status'] === 'RUNNING' ? rand(70, 100) : rand(0, 50),
                    'health_status' => $this->getHealthStatus($config['status']),
                    'hardware_profile' => $this->generateHardwareProfile(),
                    'capabilities' => $this->generateCapabilities(),
                    'water_state' => $config['status'] === 'RUNNING' ? 'circulating' : 'idle',
                    'solution_started_at' => $config['status'] === 'RUNNING' ? now()->subDays(rand(1, 30)) : null,
                    'settings' => $this->generateZoneSettings(),
                ]
            );
        }
    }

    private function getHealthStatus(string $status): string
    {
        return match ($status) {
            'RUNNING' => ['healthy', 'good', 'excellent'][rand(0, 2)],
            'PAUSED' => 'maintenance',
            'STOPPED' => 'stopped',
            default => 'unknown',
        };
    }

    private function generateHardwareProfile(): array
    {
        return [
            'sensors' => [
                'ph' => rand(1, 2),
                'ec' => rand(1, 2),
                'temperature' => rand(1, 3),
                'humidity' => rand(1, 2),
            ],
            'actuators' => [
                'pumps' => rand(1, 3),
                'lights' => rand(2, 6),
                'fans' => rand(1, 2),
            ],
        ];
    }

    private function generateCapabilities(): array
    {
        return [
            'ph_control' => rand(0, 1) === 1,
            'ec_control' => rand(0, 1) === 1,
            'climate_control' => rand(0, 1) === 1,
            'light_control' => rand(0, 1) === 1,
            'irrigation_control' => true,
            'recirculation' => rand(0, 1) === 1,
            'flow_sensor' => rand(0, 1) === 1,
        ];
    }

    private function generateZoneSettings(): array
    {
        return [
            'auto_mode' => rand(0, 1) === 1,
            'notifications_enabled' => true,
            'alert_thresholds' => [
                'ph' => ['min' => 5.0, 'max' => 7.0],
                'ec' => ['min' => 0.5, 'max' => 3.0],
                'temperature' => ['min' => 15, 'max' => 30],
            ],
        ];
    }
}

