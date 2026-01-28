<?php

namespace Database\Seeders;

use App\Models\Greenhouse;
use App\Models\InfrastructureInstance;
use Illuminate\Database\Seeder;

/**
 * Сидер для базовых экземпляров инфраструктуры теплиц
 */
class ExtendedInfrastructureAssetsSeeder extends Seeder
{
    public function run(): void
    {
        $this->command->info('=== Создание базовой инфраструктуры теплиц ===');

        $greenhouses = Greenhouse::all();
        if ($greenhouses->isEmpty()) {
            $this->command->warn('Теплицы не найдены. Запустите ExtendedGreenhousesZonesSeeder сначала.');

            return;
        }

        $created = 0;

        $assetTypes = [
            [
                'asset_type' => 'VENT',
                'label' => 'Система вентиляции',
                'required' => false,
                'specs' => [
                    'description' => 'Вентиляция для циркуляции воздуха',
                    'power_watts' => 30,
                    'airflow_cfm' => 200,
                ],
            ],
            [
                'asset_type' => 'FAN',
                'label' => 'Циркуляционный вентилятор',
                'required' => false,
                'specs' => [
                    'description' => 'Вентилятор для равномерного распределения воздуха',
                    'power_watts' => 40,
                    'airflow_cfm' => 250,
                ],
            ],
            [
                'asset_type' => 'HEATER',
                'label' => 'Обогреватель теплицы',
                'required' => false,
                'specs' => [
                    'description' => 'Обогреватель для поддержания температуры',
                    'power_watts' => 1200,
                    'type' => 'electric',
                ],
            ],
            [
                'asset_type' => 'CO2_INJECTOR',
                'label' => 'Подача CO2',
                'required' => false,
                'specs' => [
                    'description' => 'Система подачи CO2',
                    'flow_rate_lph' => 5,
                ],
            ],
            [
                'asset_type' => 'LIGHT',
                'label' => 'Общее освещение',
                'required' => false,
                'specs' => [
                    'description' => 'Освещение для общей зоны теплицы',
                    'power_watts' => 300,
                    'spectrum' => 'full',
                ],
            ],
        ];

        foreach ($greenhouses as $greenhouse) {
            foreach ($assetTypes as $asset) {
                InfrastructureInstance::firstOrCreate(
                    [
                        'owner_type' => 'greenhouse',
                        'owner_id' => $greenhouse->id,
                        'asset_type' => $asset['asset_type'],
                        'label' => $asset['label'],
                    ],
                    [
                        'required' => $asset['required'] ?? false,
                        'capacity_liters' => $asset['capacity_liters'] ?? null,
                        'flow_rate' => $asset['flow_rate'] ?? null,
                        'specs' => $asset['specs'] ?? null,
                    ]
                );
                $created++;
            }
        }

        $this->command->info("Создано экземпляров инфраструктуры: {$created}");
        $this->command->info('Всего инфраструктуры теплиц: '.InfrastructureInstance::where('owner_type', 'greenhouse')->count());
    }
}
