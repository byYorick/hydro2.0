<?php

namespace Database\Seeders;

use App\Models\InfrastructureAsset;
use Illuminate\Database\Seeder;

/**
 * Сидер для глобального каталога типов оборудования
 */
class ExtendedInfrastructureAssetsSeeder extends Seeder
{
    public function run(): void
    {
        $this->command->info('=== Создание каталога типов оборудования ===');

        $created = 0;

        $assetTypes = [
            [
                'type' => 'PUMP',
                'name' => 'Насос основной',
                'metadata' => [
                    'description' => 'Основной насос для циркуляции питательного раствора',
                    'power_watts' => 100,
                    'max_flow_lpm' => 50,
                ],
            ],
            [
                'type' => 'PUMP',
                'name' => 'Насос дренажный',
                'metadata' => [
                    'description' => 'Дренажный насос для откачки воды',
                    'power_watts' => 50,
                    'max_flow_lpm' => 30,
                ],
            ],
            [
                'type' => 'MISTER',
                'name' => 'Распылитель тумана',
                'metadata' => [
                    'description' => 'Система распыления для поддержания влажности',
                    'power_watts' => 20,
                    'nozzle_count' => 4,
                ],
            ],
            [
                'type' => 'TANK_NUTRIENT',
                'name' => 'Резервуар питательных веществ',
                'metadata' => [
                    'description' => 'Резервуар для хранения питательного раствора',
                    'capacity_liters' => 100,
                    'material' => 'plastic',
                ],
            ],
            [
                'type' => 'TANK_CLEAN',
                'name' => 'Резервуар чистой воды',
                'metadata' => [
                    'description' => 'Резервуар для хранения чистой воды',
                    'capacity_liters' => 200,
                    'material' => 'plastic',
                ],
            ],
            [
                'type' => 'DRAIN',
                'name' => 'Дренажная система',
                'metadata' => [
                    'description' => 'Система дренажа для отвода излишков воды',
                    'diameter_mm' => 50,
                ],
            ],
            [
                'type' => 'LIGHT',
                'name' => 'Светодиодная панель',
                'metadata' => [
                    'description' => 'LED панель для освещения растений',
                    'power_watts' => 200,
                    'spectrum' => 'full',
                    'coverage_m2' => 1,
                ],
            ],
            [
                'type' => 'VENT',
                'name' => 'Вентилятор',
                'metadata' => [
                    'description' => 'Вентилятор для циркуляции воздуха',
                    'power_watts' => 30,
                    'airflow_cfm' => 200,
                ],
            ],
            [
                'type' => 'HEATER',
                'name' => 'Обогреватель',
                'metadata' => [
                    'description' => 'Электрический обогреватель для поддержания температуры',
                    'power_watts' => 1000,
                    'type' => 'electric',
                ],
            ],
            [
                'type' => 'COOLER',
                'name' => 'Охладитель',
                'metadata' => [
                    'description' => 'Система охлаждения для снижения температуры',
                    'power_watts' => 500,
                    'type' => 'evaporative',
                ],
            ],
        ];

        foreach ($assetTypes as $asset) {
            InfrastructureAsset::firstOrCreate(
                [
                    'type' => $asset['type'],
                    'name' => $asset['name'],
                ],
                [
                    'metadata' => $asset['metadata'],
                ]
            );
            $created++;
        }

        $this->command->info("Создано типов оборудования: {$created}");
        $this->command->info("Всего типов оборудования: " . InfrastructureAsset::count());
    }
}

