<?php

namespace Database\Seeders;

use App\Models\ChannelBinding;
use App\Models\DeviceNode;
use App\Models\InfrastructureInstance;
use App\Models\NodeChannel;
use App\Models\Zone;
use Illuminate\Database\Seeder;

/**
 * Расширенный сидер для инфраструктуры зон и привязок каналов
 */
class ExtendedInfrastructureSeeder extends Seeder
{
    public function run(): void
    {
        $this->command->info('=== Создание расширенной инфраструктуры ===');

        $zones = Zone::all();
        if ($zones->isEmpty()) {
            $this->command->warn('Зоны не найдены.');

            return;
        }

        $infrastructureCreated = 0;
        $bindingsCreated = 0;

        foreach ($zones as $zone) {
            $infrastructureCreated += $this->seedInfrastructureForZone($zone);
            $bindingsCreated += $this->seedChannelBindingsForZone($zone);
        }

        $this->command->info("Создано инфраструктуры: {$infrastructureCreated}");
        $this->command->info("Создано привязок каналов: {$bindingsCreated}");
        $this->command->info('Всего инфраструктуры: '.InfrastructureInstance::where('owner_type', 'zone')->count());
        $this->command->info('Всего привязок: '.ChannelBinding::count());
    }

    private function seedInfrastructureForZone(Zone $zone): int
    {
        $created = 0;

        // Определяем набор оборудования в зависимости от статуса зоны
        $assetTypes = match ($zone->status) {
            'RUNNING' => [
                ['asset_type' => 'TANK_WORKING', 'label' => 'Основной резервуар', 'required' => true, 'capacity' => rand(100, 500)],
                ['asset_type' => 'TANK_NUTRIENT', 'label' => 'Резервуар питательных веществ A', 'required' => true, 'capacity' => rand(20, 100)],
                ['asset_type' => 'TANK_NUTRIENT', 'label' => 'Резервуар питательных веществ B', 'required' => true, 'capacity' => rand(20, 100)],
                ['asset_type' => 'PUMP', 'label' => 'Основной насос', 'required' => true, 'flow_rate' => rand(50, 200)],
                ['asset_type' => 'DRAIN', 'label' => 'Дренаж', 'required' => true, 'flow_rate' => rand(30, 100)],
                ['asset_type' => 'MISTER', 'label' => 'Туман', 'required' => false, 'flow_rate' => rand(5, 30)],
                ['asset_type' => 'LIGHT', 'label' => 'Освещение', 'required' => false],
                ['asset_type' => 'VENT', 'label' => 'Вентиляция', 'required' => false],
                ['asset_type' => 'HEATER', 'label' => 'Обогреватель', 'required' => false],
            ],
            'PAUSED' => [
                ['asset_type' => 'TANK_WORKING', 'label' => 'Основной резервуар', 'required' => true, 'capacity' => rand(100, 500)],
                ['asset_type' => 'PUMP', 'label' => 'Основной насос', 'required' => true, 'flow_rate' => rand(50, 200)],
            ],
            'STOPPED' => [
                ['asset_type' => 'TANK_WORKING', 'label' => 'Основной резервуар', 'required' => false, 'capacity' => rand(100, 500)],
            ],
            default => [],
        };

        foreach ($assetTypes as $assetData) {
            $specs = $this->generateAssetSpecs($assetData['asset_type']);

            InfrastructureInstance::firstOrCreate(
                [
                    'owner_type' => 'zone',
                    'owner_id' => $zone->id,
                    'asset_type' => $assetData['asset_type'],
                    'label' => $assetData['label'],
                ],
                [
                    'required' => $assetData['required'] ?? false,
                    'capacity_liters' => $assetData['capacity'] ?? null,
                    'flow_rate' => $assetData['flow_rate'] ?? null,
                    'specs' => $specs,
                ]
            );

            $created++;
        }

        return $created;
    }

    private function seedChannelBindingsForZone(Zone $zone): int
    {
        $created = 0;

        $infrastructure = InfrastructureInstance::forZone($zone->id)->get();
        $nodes = DeviceNode::where('zone_id', $zone->id)->get();

        if ($infrastructure->isEmpty() || $nodes->isEmpty()) {
            return 0;
        }

        // Маппинг типов оборудования на роли и каналы
        $bindingMap = [
            'Основной насос' => [
                'role' => 'main_pump',
                'channel' => 'pump1',
                'direction' => 'actuator',
            ],
            'Дренаж' => [
                'role' => 'drain',
                'channel' => 'pump2',
                'direction' => 'actuator',
            ],
            'Туман' => [
                'role' => 'mist',
                'channel' => 'mist',
                'direction' => 'actuator',
            ],
            'Освещение' => [
                'role' => 'light',
                'channel' => 'light',
                'direction' => 'actuator',
            ],
            'Вентиляция' => [
                'role' => 'vent',
                'channel' => 'fan',
                'direction' => 'actuator',
            ],
            'Обогреватель' => [
                'role' => 'heater',
                'channel' => 'heater',
                'direction' => 'actuator',
            ],
        ];

        foreach ($infrastructure as $asset) {
            if (! isset($bindingMap[$asset->label])) {
                continue;
            }

            $bindingConfig = $bindingMap[$asset->label];

            // Находим узел с подходящим каналом
            $node = $this->findNodeWithChannel($nodes, $bindingConfig['channel']);
            if (! $node) {
                continue;
            }

            // Проверяем, что канал существует
            $channel = NodeChannel::where('node_id', $node->id)
                ->where('channel', $bindingConfig['channel'])
                ->first();

            if (! $channel) {
                continue;
            }

            // Учитываем уникальный индекс channel_bindings.node_channel_id.
            ChannelBinding::updateOrCreate(
                [
                    'node_channel_id' => $channel->id,
                ],
                [
                    'infrastructure_instance_id' => $asset->id,
                    'direction' => $bindingConfig['direction'],
                    'role' => $bindingConfig['role'],
                ]
            );

            $created++;
        }

        return $created;
    }

    private function findNodeWithChannel($nodes, string $channel): ?DeviceNode
    {
        foreach ($nodes as $node) {
            $hasChannel = NodeChannel::where('node_id', $node->id)
                ->where('channel', $channel)
                ->exists();

            if ($hasChannel) {
                return $node;
            }
        }

        return $nodes->first();
    }

    private function generateAssetSpecs(string $assetType): array
    {
        return match ($assetType) {
            'TANK_WORKING', 'TANK_NUTRIENT', 'TANK_CLEAN' => [
                'material' => 'plastic',
                'level_sensor' => true,
            ],
            'PUMP', 'DRAIN', 'MISTER' => [
                'power_watts' => rand(50, 200),
                'max_pressure' => rand(2, 6),
            ],
            'LIGHT' => [
                'power_watts' => rand(100, 300),
                'spectrum' => 'full',
            ],
            'VENT', 'FAN' => [
                'power_watts' => rand(20, 100),
                'airflow_cfm' => rand(100, 500),
            ],
            'HEATER' => [
                'power_watts' => rand(500, 2000),
                'type' => 'electric',
            ],
            default => [],
        };
    }
}
