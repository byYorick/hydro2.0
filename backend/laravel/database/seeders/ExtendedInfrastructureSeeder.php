<?php

namespace Database\Seeders;

use App\Models\DeviceNode;
use App\Models\NodeChannel;
use App\Models\Zone;
use App\Models\ZoneChannelBinding;
use App\Models\ZoneInfrastructure;
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
        $this->command->info("Всего инфраструктуры: " . ZoneInfrastructure::count());
        $this->command->info("Всего привязок: " . ZoneChannelBinding::count());
    }

    private function seedInfrastructureForZone(Zone $zone): int
    {
        $created = 0;

        // Определяем набор оборудования в зависимости от статуса зоны
        $assetTypes = match ($zone->status) {
            'RUNNING' => [
                ['type' => 'main_reservoir', 'required' => true, 'capacity' => rand(100, 500)],
                ['type' => 'nutrient_tank_a', 'required' => true, 'capacity' => rand(20, 100)],
                ['type' => 'nutrient_tank_b', 'required' => true, 'capacity' => rand(20, 100)],
                ['type' => 'ph_up_tank', 'required' => true, 'capacity' => rand(10, 50)],
                ['type' => 'ph_down_tank', 'required' => true, 'capacity' => rand(10, 50)],
                ['type' => 'main_pump', 'required' => true, 'flow_rate' => rand(50, 200)],
                ['type' => 'drain_pump', 'required' => false, 'flow_rate' => rand(30, 100)],
                ['type' => 'light_panel_1', 'required' => false],
                ['type' => 'light_panel_2', 'required' => false],
                ['type' => 'fan_1', 'required' => false],
                ['type' => 'heater', 'required' => false],
            ],
            'PAUSED' => [
                ['type' => 'main_reservoir', 'required' => true, 'capacity' => rand(100, 500)],
                ['type' => 'main_pump', 'required' => true, 'flow_rate' => rand(50, 200)],
            ],
            'STOPPED' => [
                ['type' => 'main_reservoir', 'required' => false, 'capacity' => rand(100, 500)],
            ],
            default => [],
        };

        foreach ($assetTypes as $assetData) {
            $specs = $this->generateAssetSpecs($assetData['type']);

            ZoneInfrastructure::firstOrCreate(
                [
                    'zone_id' => $zone->id,
                    'asset_type' => $assetData['type'],
                ],
                [
                    'label' => $this->getAssetLabel($assetData['type']),
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

        $infrastructure = ZoneInfrastructure::where('zone_id', $zone->id)->get();
        $nodes = DeviceNode::where('zone_id', $zone->id)->get();

        if ($infrastructure->isEmpty() || $nodes->isEmpty()) {
            return 0;
        }

        // Маппинг типов оборудования на роли и каналы
        $bindingMap = [
            'main_pump' => [
                'role' => ZoneChannelBinding::ROLE_MAIN_PUMP,
                'channel' => 'pump1',
                'direction' => ZoneChannelBinding::DIRECTION_ACTUATOR,
            ],
            'drain_pump' => [
                'role' => ZoneChannelBinding::ROLE_DRAIN_PUMP,
                'channel' => 'pump2',
                'direction' => ZoneChannelBinding::DIRECTION_ACTUATOR,
            ],
            'ph_sensor' => [
                'role' => ZoneChannelBinding::ROLE_PH_SENSOR,
                'channel' => 'ph',
                'direction' => ZoneChannelBinding::DIRECTION_SENSOR,
            ],
            'ec_sensor' => [
                'role' => ZoneChannelBinding::ROLE_EC_SENSOR,
                'channel' => 'ec',
                'direction' => ZoneChannelBinding::DIRECTION_SENSOR,
            ],
            'temp_sensor' => [
                'role' => ZoneChannelBinding::ROLE_TEMP_SENSOR,
                'channel' => 'temperature',
                'direction' => ZoneChannelBinding::DIRECTION_SENSOR,
            ],
            'fan_1' => [
                'role' => ZoneChannelBinding::ROLE_FAN,
                'channel' => 'fan',
                'direction' => ZoneChannelBinding::DIRECTION_ACTUATOR,
            ],
            'heater' => [
                'role' => ZoneChannelBinding::ROLE_HEATER,
                'channel' => 'heater',
                'direction' => ZoneChannelBinding::DIRECTION_ACTUATOR,
            ],
            'light_panel_1' => [
                'role' => ZoneChannelBinding::ROLE_LIGHT,
                'channel' => 'light',
                'direction' => ZoneChannelBinding::DIRECTION_ACTUATOR,
            ],
        ];

        foreach ($infrastructure as $asset) {
            if (!isset($bindingMap[$asset->asset_type])) {
                continue;
            }

            $bindingConfig = $bindingMap[$asset->asset_type];

            // Находим узел с подходящим каналом
            $node = $this->findNodeWithChannel($nodes, $bindingConfig['channel']);
            if (!$node) {
                continue;
            }

            // Проверяем, что канал существует
            $channel = NodeChannel::where('node_id', $node->id)
                ->where('channel', $bindingConfig['channel'])
                ->first();

            if (!$channel) {
                continue;
            }

            // Создаем привязку только если её еще нет
            ZoneChannelBinding::firstOrCreate(
                [
                    'zone_id' => $zone->id,
                    'asset_id' => $asset->id,
                ],
                [
                    'node_id' => $node->id,
                    'channel' => $bindingConfig['channel'],
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
            'main_reservoir', 'nutrient_tank_a', 'nutrient_tank_b', 'ph_up_tank', 'ph_down_tank' => [
                'material' => 'plastic',
                'level_sensor' => true,
            ],
            'main_pump', 'drain_pump' => [
                'power_watts' => rand(50, 200),
                'max_pressure' => rand(2, 6),
            ],
            'light_panel_1', 'light_panel_2' => [
                'power_watts' => rand(100, 300),
                'spectrum' => 'full',
            ],
            'fan_1' => [
                'power_watts' => rand(20, 100),
                'airflow_cfm' => rand(100, 500),
            ],
            'heater' => [
                'power_watts' => rand(500, 2000),
                'type' => 'electric',
            ],
            default => [],
        };
    }

    private function getAssetLabel(string $assetType): string
    {
        return match ($assetType) {
            'main_reservoir' => 'Основной резервуар',
            'nutrient_tank_a' => 'Резервуар питательных веществ A',
            'nutrient_tank_b' => 'Резервуар питательных веществ B',
            'ph_up_tank' => 'Резервуар pH+',
            'ph_down_tank' => 'Резервуар pH-',
            'main_pump' => 'Основной насос',
            'drain_pump' => 'Дренажный насос',
            'light_panel_1' => 'Панель освещения 1',
            'light_panel_2' => 'Панель освещения 2',
            'fan_1' => 'Вентилятор 1',
            'heater' => 'Обогреватель',
            default => ucfirst(str_replace('_', ' ', $assetType)),
        };
    }
}

