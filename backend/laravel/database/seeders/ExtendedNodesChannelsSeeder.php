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
            $node = $this->seedNodeForZone($zone);
            if ($node) {
                $nodesCreated++;
                $channels = $this->seedChannelsForNode($node);
                $channelsCreated += count($channels);
            }
        }

        // Создаем также несколько непривязанных узлов
        $unassignedNodes = $this->seedUnassignedNodes();
        $nodesCreated += count($unassignedNodes);

        $this->command->info("Создано узлов: {$nodesCreated}");
        $this->command->info("Создано каналов: {$channelsCreated}");
        $this->command->info('Всего узлов: '.DeviceNode::count());
        $this->command->info('Всего каналов: '.NodeChannel::count());
    }

    private function seedNodeForZone(Zone $zone): ?DeviceNode
    {
        $status = $zone->status === 'RUNNING'
            ? (rand(0, 10) > 1 ? 'online' : 'offline')
            : 'offline';

        $lifecycleState = match ($status) {
            'online' => NodeLifecycleState::ACTIVE,
            'offline' => NodeLifecycleState::ASSIGNED_TO_ZONE,
            default => NodeLifecycleState::REGISTERED_BACKEND,
        };

        return DeviceNode::firstOrCreate(
            [
                'zone_id' => $zone->id,
            ],
            [
                'uid' => 'nd-zone-'.$zone->id,
                'name' => "Контроллер - {$zone->name}",
                'type' => 'irrig',
                'status' => $status,
                'lifecycle_state' => $lifecycleState,
                'fw_version' => $this->generateFirmwareVersion(),
                'hardware_revision' => 'rev'.rand(1, 3),
                'hardware_id' => 'HW-'.Str::random(8),
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
    }

    private function seedChannelsForNode(DeviceNode $node): array
    {
        $channels = [];

        $channelsList = ['ph', 'ec', 'temperature', 'humidity', 'pump1', 'pump2', 'light', 'fan', 'heater', 'mist'];

        // Маппинг каналов на их конфигурацию
        $channelMapping = [
            'ph' => ['type' => 'sensor', 'metric' => 'PH', 'unit' => 'pH'],
            'ec' => ['type' => 'sensor', 'metric' => 'EC', 'unit' => 'mS/cm'],
            'temperature' => ['type' => 'sensor', 'metric' => 'TEMPERATURE', 'unit' => '°C'],
            'humidity' => ['type' => 'sensor', 'metric' => 'HUMIDITY', 'unit' => '%'],
            'pump1' => ['type' => 'actuator', 'metric' => 'PUMP1', 'unit' => ''],
            'pump2' => ['type' => 'actuator', 'metric' => 'PUMP2', 'unit' => ''],
            'light' => ['type' => 'actuator', 'metric' => 'LIGHT', 'unit' => '%'],
            'fan' => ['type' => 'actuator', 'metric' => 'FAN', 'unit' => '%'],
            'heater' => ['type' => 'actuator', 'metric' => 'HEATER', 'unit' => '%'],
            'mist' => ['type' => 'actuator', 'metric' => 'MIST', 'unit' => '%'],
        ];

        // Формируем конфигурацию каналов на основе списка
        $channelConfigs = [];
        foreach ($channelsList as $channelName) {
            if (isset($channelMapping[$channelName])) {
                $channelConfigs[] = array_merge(
                    ['channel' => $channelName],
                    $channelMapping[$channelName]
                );
            }
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
                    'uid' => 'nd-unassigned-'.Str::random(12),
                ],
                [
                    'name' => "Непривязанный узел #{$i}",
                    'type' => ['ph', 'ec', 'climate', 'irrig', 'light', 'relay', 'water_sensor', 'recirculation', 'unknown'][rand(0, 8)],
                    'status' => 'offline',
                    'lifecycle_state' => $unassignedStates[rand(0, count($unassignedStates) - 1)],
                    'fw_version' => $this->generateFirmwareVersion(),
                    'hardware_revision' => 'rev'.rand(1, 3),
                    'hardware_id' => 'HW-'.Str::random(8),
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
        return rand(1, 2).'.'.rand(0, 5).'.'.rand(0, 9);
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
            'mist' => ['max_power' => 100, 'min_power' => 0],
            default => [],
        };
    }
}
