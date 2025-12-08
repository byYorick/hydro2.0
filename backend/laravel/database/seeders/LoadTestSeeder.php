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
        $this->command->info('Создание данных для нагрузочного тестирования (100 зон)...');

        // Создаем или получаем теплицу
        $greenhouse = Greenhouse::firstOrCreate(
            ['uid' => 'gh-load-test'],
            [
                'name' => 'Load Test Greenhouse',
                'timezone' => 'Europe/Moscow',
                'type' => 'indoor',
            ]
        );

        $zones = [];
        $nodes = [];

        // Создаем 100 зон
        for ($i = 1; $i <= 100; $i++) {
            $zone = Zone::firstOrCreate(
                [
                    'greenhouse_id' => $greenhouse->id,
                    'name' => "Load Test Zone {$i}",
                ],
                [
                    'uid' => 'zone-load-test-' . Str::random(16),
                    'description' => "Zone for load testing #{$i}",
                    'status' => $i % 10 === 0 ? 'PAUSED' : 'RUNNING',
                ]
            );
            $zones[] = $zone;

            // Создаем 1-5 нод для каждой зоны
            $nodesPerZone = rand(1, 5);
            for ($j = 1; $j <= $nodesPerZone; $j++) {
                $node = DeviceNode::firstOrCreate(
                    [
                        'uid' => "node-load-test-{$i}-{$j}",
                    ],
                    [
                        'zone_id' => $zone->id,
                        'name' => "Node {$j} - Zone {$i}",
                        'type' => $j === 1 ? 'ph' : ($j === 2 ? 'ec' : 'sensor'),
                        'status' => 'ONLINE',
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
        }

        $this->command->info("✓ Создано зон: " . count($zones));
        $this->command->info("✓ Создано нод: " . count($nodes));
    }
}

