<?php

namespace Database\Seeders;

use Illuminate\Database\Seeder;
use App\Models\Greenhouse;
use App\Models\Zone;
use App\Models\DeviceNode;
use App\Models\NodeChannel;
use Illuminate\Support\Str;

/**
 * Seeder для создания 100 зон для нагрузочного тестирования
 */
class LoadTestSeeder extends Seeder
{
    public function run(): void
    {
        $this->command->info('Создание данных для нагрузочного тестирования (1000 нод)...');

        // Создаем или получаем теплицу
        $greenhouse = Greenhouse::firstOrCreate(
            ['uid' => 'gh-load-test'],
            [
                'name' => 'Load Test Greenhouse',
                'timezone' => 'Europe/Moscow',
                'type' => 'indoor',
                'provisioning_token' => Str::random(32),
            ]
        );

        $zones = [];
        $nodes = [];

        // Создаем 40 зон (для 1000 нод это примерно 25 нод на зону)
        $zonesCount = 40;
        for ($i = 1; $i <= $zonesCount; $i++) {
            $zone = Zone::firstOrCreate(
                [
                    'greenhouse_id' => $greenhouse->id,
                    'name' => "Load Test Zone {$i}",
                ],
                [
                    'uid' => 'zone-load-test-' . $i,
                    'description' => "Zone for load testing #{$i}",
                    'status' => $i % 10 === 0 ? 'PAUSED' : 'RUNNING',
                ]
            );
            $zones[] = $zone;
        }

        // Создаем 1000 нод, распределяя их по зонам
        $nodesPerZone = (int)ceil(1000 / $zonesCount);
        for ($i = 0; $i < 1000; $i++) {
            $zone = $zones[$i % $zonesCount];
            $j = (int)floor($i / $zonesCount) + 1;
                $node = DeviceNode::firstOrCreate(
                    [
                        'uid' => "node-load-test-{$i}-{$j}",
                    ],
                    [
                        'zone_id' => $zone->id,
                        'name' => "Node {$j} - Zone {$i}",
                        'type' => $j === 1 ? 'ph' : ($j === 2 ? 'ec' : 'climate'),
                        'status' => 'online',
                        'lifecycle_state' => 'ACTIVE',
                        'fw_version' => '1.0.0',
                        'last_seen_at' => now(),
                        'last_heartbeat_at' => now(),
                    ]
                );
                $nodes[] = $node;

            // Создаем каналы для ноды
            $channels = ['ph', 'ec', 'temperature', 'humidity'];
            foreach ($channels as $channelName) {
                NodeChannel::firstOrCreate(
                    [
                        'node_id' => $node->id,
                        'channel' => $channelName,
                    ],
                    [
                        'type' => 'sensor',
                        'metric' => strtoupper($channelName),
                        'unit' => match ($channelName) {
                            'ph' => 'pH',
                            'ec' => 'mS/cm',
                            'temperature' => '°C',
                            'humidity' => '%',
                            default => '',
                        },
                    ]
                );
            }
        }

        $this->command->info("✓ Создано зон: " . count($zones));
        $this->command->info("✓ Создано нод: " . count($nodes));
    }
}
