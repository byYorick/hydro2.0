<?php

namespace Database\Seeders;

use Illuminate\Database\Seeder;
use App\Models\Greenhouse;
use App\Models\Zone;
use App\Models\DeviceNode;
use App\Models\NodeChannel;
use Illuminate\Support\Str;

/**
 * Seeder для создания 100 нод для 30-минутного нагрузочного тестирования
 */
class ThirtyMinLoadTestSeeder extends Seeder
{
    public function run(): void
    {
        $this->command->info('Создание данных для 30-минутного нагрузочного тестирования (100 нод)...');

        // Создаем или получаем теплицу
        $greenhouse = Greenhouse::firstOrCreate(
            ['uid' => 'gh-30min-test'],
            [
                'name' => '30min Test Greenhouse',
                'timezone' => 'Europe/Moscow',
                'type' => 'indoor',
                'provisioning_token' => Str::random(32),
            ]
        );

        $zones = [];
        $nodes = [];

        // Создаем 10 зон (для 100 нод это 10 нод на зону)
        $zonesCount = 10;
        for ($i = 1; $i <= $zonesCount; $i++) {
            $zone = Zone::firstOrCreate(
                [
                    'greenhouse_id' => $greenhouse->id,
                    'name' => "30min Test Zone {$i}",
                ],
                [
                    'uid' => 'zone-30min-test-' . $i,
                    'description' => "Zone for 30min test #{$i}",
                    'status' => 'RUNNING',
                ]
            );
            $zones[] = $zone;
        }

        // Создаем 100 нод, распределяя их по зонам
        for ($i = 0; $i < 100; $i++) {
            $zone = $zones[$i % $zonesCount];
            
            $node = DeviceNode::firstOrCreate(
                [
                    'uid' => "node-30min-test-{$i}",
                ],
                [
                    'zone_id' => $zone->id,
                    'name' => "Node {$i} - Zone " . $zone->name,
                    'type' => $i % 4 === 0 ? 'ph' : ($i % 4 === 1 ? 'ec' : 'sensor'),
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
