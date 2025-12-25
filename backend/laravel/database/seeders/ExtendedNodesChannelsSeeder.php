<?php

namespace Database\Seeders;

use App\Enums\NodeLifecycleState;
use App\Models\DeviceNode;
use App\Models\NodeChannel;
use App\Models\Zone;
use Illuminate\Database\Seeder;
use Illuminate\Support\Str;

/**
 * Расширенный сидер для узлов и каналов
 * Создает разнообразные узлы с каналами для всех зон
 */
class ExtendedNodesChannelsSeeder extends Seeder
{
    public function run(): void
    {
        $this->command->info('=== Создание расширенных узлов и каналов ===');

        $zones = Zone::all();
        if ($zones->isEmpty()) {
            $this->command->warn('Зоны не найдены. Запустите ExtendedGreenhousesZonesSeeder сначала.');
            return;
        }

        $nodesCreated = 0;
        $channelsCreated = 0;

        foreach ($zones as $zone) {
            $nodes = $this->seedNodesForZone($zone);
            $nodesCreated += count($nodes);
            
            foreach ($nodes as $node) {
                $channels = $this->seedChannelsForNode($node);
                $channelsCreated += count($channels);
            }
        }

        // Создаем также несколько непривязанных узлов
        $unassignedNodes = $this->seedUnassignedNodes();
        $nodesCreated += count($unassignedNodes);

        $this->command->info("Создано узлов: {$nodesCreated}");
        $this->command->info("Создано каналов: {$channelsCreated}");
        $this->command->info("Всего узлов: " . DeviceNode::count());
        $this->command->info("Всего каналов: " . NodeChannel::count());
    }

    private function seedNodesForZone(Zone $zone): array
    {
        $nodes = [];
        
        // Определяем количество узлов в зависимости от статуса зоны
        $nodeCount = match ($zone->status) {
            'RUNNING' => rand(3, 6),
            'PAUSED' => rand(2, 4),
            'STOPPED' => rand(1, 2),
            default => 2,
        };

        $nodeTypes = [
            [
                'type' => 'sensor',
                'name_prefix' => 'Датчик',
                'channels' => ['ph', 'ec', 'temperature', 'humidity'],
            ],
            [
                'type' => 'actuator',
                'name_prefix' => 'Актуатор',
                'channels' => ['pump1', 'pump2', 'light', 'fan'],
            ],
            [
                'type' => 'controller',
                'name_prefix' => 'Контроллер',
                'channels' => ['ph', 'ec', 'pump1', 'pump2', 'light', 'fan', 'heater'],
            ],
            [
                'type' => 'sensor',
                'name_prefix' => 'Датчик pH/EC',
                'channels' => ['ph', 'ec'],
            ],
            [
                'type' => 'actuator',
                'name_prefix' => 'Насос',
                'channels' => ['pump1', 'pump2'],
            ],
            [
                'type' => 'sensor',
                'name_prefix' => 'Датчик Климата',
                'channels' => ['temperature', 'humidity'],
            ],
        ];

        for ($i = 0; $i < $nodeCount; $i++) {
            $nodeType = $nodeTypes[$i % count($nodeTypes)];
            $status = $zone->status === 'RUNNING' 
                ? (rand(0, 10) > 1 ? 'online' : 'offline')
                : 'offline';
            
            $lifecycleState = match ($status) {
                'online' => NodeLifecycleState::ACTIVE,
                'offline' => NodeLifecycleState::ASSIGNED_TO_ZONE,
                default => NodeLifecycleState::REGISTERED_BACKEND,
            };

            $node = DeviceNode::firstOrCreate(
                [
                    'zone_id' => $zone->id,
                    'uid' => 'nd-' . Str::random(12) . '-' . $zone->id,
                ],
                [
                    'name' => "{$nodeType['name_prefix']} - {$zone->name} #{$i}",
                    'type' => $nodeType['type'],
                    'status' => $status,
                    'lifecycle_state' => $lifecycleState,
                    'fw_version' => $this->generateFirmwareVersion(),
                    'hardware_revision' => 'rev' . rand(1, 3),
                    'hardware_id' => 'HW-' . Str::random(8),
                    'last_seen_at' => $status === 'online' ? now()->subMinutes(rand(1, 30)) : now()->subHours(rand(2, 48)),
                    'last_heartbeat_at' => $status === 'online' ? now()->subMinutes(rand(1, 5)) : now()->subHours(rand(1, 24)),
                    'first_seen_at' => now()->subDays(rand(1, 90)),
                    'validated' => true,
                    'uptime_seconds' => $status === 'online' ? rand(3600, 86400 * 7) : 0,
                    'free_heap_bytes' => rand(10000, 50000),
                    'rssi' => $status === 'online' ? rand(-70, -30) : rand(-90, -80),
                    'config' => $this->generateNodeConfig($zone),
                ]
            );

            $nodes[] = $node;
        }

        return $nodes;
    }

    private function seedChannelsForNode(DeviceNode $node): array
    {
        $channels = [];
        
        // Определяем каналы в зависимости от типа узла
        $channelConfigs = match ($node->type) {
            'sensor' => [
                ['channel' => 'ph', 'type' => 'sensor', 'metric' => 'PH', 'unit' => 'pH'],
                ['channel' => 'ec', 'type' => 'sensor', 'metric' => 'EC', 'unit' => 'mS/cm'],
                ['channel' => 'temperature', 'type' => 'sensor', 'metric' => 'TEMPERATURE', 'unit' => '°C'],
                ['channel' => 'humidity', 'type' => 'sensor', 'metric' => 'HUMIDITY', 'unit' => '%'],
            ],
            'actuator' => [
                ['channel' => 'pump1', 'type' => 'actuator', 'metric' => 'PUMP1', 'unit' => ''],
                ['channel' => 'pump2', 'type' => 'actuator', 'metric' => 'PUMP2', 'unit' => ''],
                ['channel' => 'light', 'type' => 'actuator', 'metric' => 'LIGHT', 'unit' => '%'],
                ['channel' => 'fan', 'type' => 'actuator', 'metric' => 'FAN', 'unit' => '%'],
            ],
            'controller' => [
                ['channel' => 'ph', 'type' => 'sensor', 'metric' => 'PH', 'unit' => 'pH'],
                ['channel' => 'ec', 'type' => 'sensor', 'metric' => 'EC', 'unit' => 'mS/cm'],
                ['channel' => 'pump1', 'type' => 'actuator', 'metric' => 'PUMP1', 'unit' => ''],
                ['channel' => 'pump2', 'type' => 'actuator', 'metric' => 'PUMP2', 'unit' => ''],
                ['channel' => 'light', 'type' => 'actuator', 'metric' => 'LIGHT', 'unit' => '%'],
                ['channel' => 'fan', 'type' => 'actuator', 'metric' => 'FAN', 'unit' => '%'],
                ['channel' => 'heater', 'type' => 'actuator', 'metric' => 'HEATER', 'unit' => '%'],
            ],
            default => [],
        };

        // Для некоторых узлов используем подмножество каналов
        if (count($channelConfigs) > 4 && rand(0, 1) === 1) {
            $channelConfigs = array_slice($channelConfigs, 0, rand(2, 4));
        }

        foreach ($channelConfigs as $config) {
            $channel = NodeChannel::firstOrCreate(
                [
                    'node_id' => $node->id,
                    'channel' => $config['channel'],
                ],
                [
                    'type' => $config['type'],
                    'metric' => $config['metric'],
                    'unit' => $config['unit'],
                    'config' => $this->generateChannelConfig($config['channel']),
                ]
            );
            $channels[] = $channel;
        }

        return $channels;
    }

    private function seedUnassignedNodes(): array
    {
        $nodes = [];
        
        // Создаем несколько непривязанных узлов в разных состояниях
        $unassignedStates = [
            NodeLifecycleState::UNPROVISIONED,
            NodeLifecycleState::PROVISIONED_WIFI,
            NodeLifecycleState::REGISTERED_BACKEND,
        ];

        for ($i = 0; $i < 5; $i++) {
            $node = DeviceNode::firstOrCreate(
                [
                    'uid' => 'nd-unassigned-' . Str::random(12),
                ],
                [
                    'name' => "Непривязанный узел #{$i}",
                    'type' => ['sensor', 'actuator', 'controller'][rand(0, 2)],
                    'status' => 'offline',
                    'lifecycle_state' => $unassignedStates[rand(0, count($unassignedStates) - 1)],
                    'fw_version' => $this->generateFirmwareVersion(),
                    'hardware_revision' => 'rev' . rand(1, 3),
                    'hardware_id' => 'HW-' . Str::random(8),
                    'last_seen_at' => now()->subDays(rand(1, 30)),
                    'first_seen_at' => now()->subDays(rand(1, 90)),
                    'validated' => false,
                    'config' => [],
                ]
            );
            $nodes[] = $node;
        }

        return $nodes;
    }

    private function generateFirmwareVersion(): string
    {
        return rand(1, 2) . '.' . rand(0, 5) . '.' . rand(0, 9);
    }

    private function generateNodeConfig(Zone $zone): array
    {
        return [
            'zone_uid' => $zone->uid,
            'greenhouse_id' => $zone->greenhouse_id,
            'mqtt_topic' => "hydro/{$zone->uid}/node",
            'telemetry_interval' => rand(30, 300),
        ];
    }

    private function generateChannelConfig(string $channel): array
    {
        return match ($channel) {
            'ph' => ['min' => 0, 'max' => 14, 'calibration' => rand(0, 1) === 1],
            'ec' => ['min' => 0, 'max' => 5, 'calibration' => rand(0, 1) === 1],
            'temperature' => ['min' => -10, 'max' => 50, 'calibration' => rand(0, 1) === 1],
            'humidity' => ['min' => 0, 'max' => 100],
            'pump1', 'pump2' => ['max_speed' => 100, 'min_speed' => 0],
            'light' => ['max_intensity' => 100, 'min_intensity' => 0],
            'fan' => ['max_speed' => 100, 'min_speed' => 0],
            'heater' => ['max_power' => 100, 'min_power' => 0],
            default => [],
        };
    }
}

