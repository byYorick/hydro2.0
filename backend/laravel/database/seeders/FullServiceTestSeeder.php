<?php

namespace Database\Seeders;

use App\Models\Alert;
use App\Models\Command;
use App\Models\DeviceNode;
use App\Models\Greenhouse;
use App\Models\NodeChannel;
use App\Models\Preset;
use App\Models\Recipe;
use App\Models\RecipePhase;
use App\Models\TelemetryLast;
use App\Models\TelemetrySample;
use App\Models\User;
use App\Models\Zone;
use App\Models\ZoneEvent;
use App\Models\ZoneRecipeInstance;
use Illuminate\Database\Seeder;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Str;

/**
 * Полный сидер для тестирования всех сервисов системы
 *
 * Заполняет все таблицы данными для проверки:
 * - Laravel API (greenhouses, zones, nodes, recipes, alerts, commands)
 * - MQTT Bridge (nodes, commands, telemetry)
 * - History Logger (telemetry_samples, telemetry_last)
 * - Automation Engine (zones, recipes, commands, alerts)
 * - Scheduler (zones, recipes, commands)
 * - Digital Twin (zones, nodes, telemetry, simulations)
 * - Telemetry Aggregator (telemetry_samples, aggregated tables)
 * - Prometheus/Grafana (metrics, alerts, events)
 */
class FullServiceTestSeeder extends Seeder
{
    public function run(): void
    {
        $this->command->info('=== Заполнение данных для тестирования всех сервисов ===');

        // 1. Пользователи
        $this->seedUsers();

        // 2. Пресеты (должны быть созданы через PresetSeeder)
        $presets = $this->seedPresets();

        // 3. Теплицы и зоны
        $greenhouses = $this->seedGreenhouses();

        // 4. Зоны с пресетами
        $zones = $this->seedZones($greenhouses, $presets);

        // 5. Узлы и каналы
        $nodes = $this->seedNodes($zones);

        // 6. Рецепты и фазы
        $recipes = $this->seedRecipes();

        // 7. Экземпляры рецептов в зонах
        $this->seedRecipeInstances($zones, $recipes);

        // 8. Телеметрия (samples и last)
        $this->seedTelemetry($zones, $nodes);

        // 9. Команды
        $this->seedCommands($zones, $nodes);

        // 10. Алерты
        $this->seedAlerts($zones);

        // 11. События зон
        $this->seedZoneEvents($zones);

        // 12. Модели и симуляции
        $this->seedModelsAndSimulations($zones);

        // 13. Прогнозы AI
        $this->seedPredictions($zones);

        // 14. Урожаи
        $this->seedHarvests($zones);

        // 15. Файлы прошивок
        $this->seedFirmwareFiles($nodes);

        // 16. Логи
        $this->seedLogs($zones, $nodes);

        $this->command->info('=== Заполнение завершено! ===');
        $this->printStatistics();
    }

    private function seedUsers(): void
    {
        $this->command->info('Создание пользователей...');

        User::firstOrCreate(
            ['email' => 'admin@hydro.local'],
            [
                'name' => 'Admin User',
                'password' => bcrypt('password'),
                'role' => 'admin',
                'email_verified_at' => now(),
            ]
        );

        User::firstOrCreate(
            ['email' => 'operator@hydro.local'],
            [
                'name' => 'Operator User',
                'password' => bcrypt('password'),
                'role' => 'operator',
                'email_verified_at' => now(),
            ]
        );

        User::firstOrCreate(
            ['email' => 'viewer@hydro.local'],
            [
                'name' => 'Viewer User',
                'password' => bcrypt('password'),
                'role' => 'viewer',
                'email_verified_at' => now(),
            ]
        );
    }

    private function seedGreenhouses(): array
    {
        $this->command->info('Создание теплиц...');

        $greenhouse1 = Greenhouse::firstOrCreate(
            ['uid' => 'gh-main-001'],
            [
                'name' => 'Main Greenhouse',
                'timezone' => 'Europe/Moscow',
                'type' => 'indoor',
                'coordinates' => ['lat' => 55.7558, 'lon' => 37.6173],
                'provisioning_token' => 'gh_'.\Illuminate\Support\Str::random(32),
                'description' => 'Main production greenhouse',
            ]
        );

        $greenhouse2 = Greenhouse::firstOrCreate(
            ['uid' => 'gh-secondary-001'],
            [
                'name' => 'Secondary Greenhouse',
                'timezone' => 'Europe/Moscow',
                'type' => 'outdoor',
                'coordinates' => ['lat' => 55.7558, 'lon' => 37.6174],
                'provisioning_token' => 'gh_'.\Illuminate\Support\Str::random(32),
                'description' => 'Secondary production greenhouse',
            ]
        );

        return [$greenhouse1, $greenhouse2];
    }

    private function seedPresets(): \Illuminate\Database\Eloquent\Collection
    {
        $this->command->info('Создание пресетов...');

        // Используем существующие пресеты (созданы через PresetSeeder)
        $presets = Preset::all();

        if ($presets->isEmpty()) {
            $this->command->warn('Пресеты не найдены. Запустите PresetSeeder сначала.');
        }

        return $presets;
    }

    private function seedZones(array $greenhouses, \Illuminate\Database\Eloquent\Collection $presets): array
    {
        $this->command->info('Создание зон...');

        $zones = [];
        $zoneData = [
            ['name' => 'Zone A - Lettuce', 'status' => 'RUNNING', 'preset' => 0],
            ['name' => 'Zone B - Basil', 'status' => 'PAUSED', 'preset' => 1],
            ['name' => 'Zone C - Tomatoes', 'status' => 'RUNNING', 'preset' => 2],
            ['name' => 'Zone D - Cucumbers', 'status' => 'RUNNING', 'preset' => 3],
            ['name' => 'Zone E - Peppers', 'status' => 'STOPPED', 'preset' => 4],
        ];

        foreach ($zoneData as $index => $data) {
            $greenhouse = $greenhouses[$index < 3 ? 0 : 1];
            $preset = $presets->isNotEmpty() ? $presets->get($data['preset'] % $presets->count()) : null;

            $zones[] = Zone::firstOrCreate(
                [
                    'greenhouse_id' => $greenhouse->id,
                    'name' => $data['name'],
                ],
                [
                    'uid' => 'zone-'.\Illuminate\Support\Str::random(16),
                    'description' => "Production zone for {$data['name']}",
                    'status' => $data['status'],
                    'preset_id' => $preset ? $preset->id : null,
                ]
            );
        }

        return $zones;
    }

    private function seedNodes(array $zones): array
    {
        $this->command->info('Создание узлов и каналов...');

        $nodes = [];
        $nodeTypes = [
            ['type' => 'sensor', 'uid' => 'nd-ph-001', 'name' => 'pH Sensor 1', 'channels' => ['ph']],
            ['type' => 'sensor', 'uid' => 'nd-ec-001', 'name' => 'EC Sensor 1', 'channels' => ['ec']],
            ['type' => 'sensor', 'uid' => 'nd-temp-001', 'name' => 'Temperature Sensor 1', 'channels' => ['temperature', 'humidity']],
            ['type' => 'actuator', 'uid' => 'nd-pump-001', 'name' => 'Pump 1', 'channels' => ['pump1', 'pump2']],
            ['type' => 'controller', 'uid' => 'nd-combo-001', 'name' => 'Combo Controller', 'channels' => ['ph', 'ec', 'pump1', 'pump2', 'light']],
        ];

        $statuses = ['ONLINE', 'ONLINE', 'OFFLINE', 'ONLINE', 'DEGRADED'];
        $lifecycleStates = ['ACTIVE', 'ACTIVE', 'UNPROVISIONED', 'ASSIGNED_TO_ZONE', 'ACTIVE'];

        foreach ($zones as $zoneIndex => $zone) {
            $nodeData = $nodeTypes[$zoneIndex % count($nodeTypes)];
            $status = $statuses[$zoneIndex % count($statuses)];
            $lifecycle = $lifecycleStates[$zoneIndex % count($lifecycleStates)];

            $node = DeviceNode::firstOrCreate(
                ['uid' => $nodeData['uid'].'-'.$zone->id],
                [
                    'zone_id' => $zone->id,
                    'name' => $nodeData['name'].' - Zone '.$zone->name,
                    'type' => $nodeData['type'],
                    'status' => $status,
                    'lifecycle_state' => $lifecycle,
                    'fw_version' => '1.2.3',
                    'last_seen_at' => $status === 'ONLINE' ? now() : now()->subHours(2),
                    'last_heartbeat_at' => $status === 'ONLINE' ? now() : now()->subHours(2),
                ]
            );

            // Создаем каналы для узла
            foreach ($nodeData['channels'] as $channelName) {
                $channelType = in_array($channelName, ['pump1', 'pump2', 'light']) ? 'actuator' : 'sensor';
                NodeChannel::firstOrCreate(
                    [
                        'node_id' => $node->id,
                        'channel' => $channelName,
                    ],
                    [
                        'type' => $channelType,
                        'metric' => strtoupper($channelName),
                        'unit' => match ($channelName) {
                            'ph' => 'pH',
                            'ec' => 'mS/cm',
                            'temperature' => '°C',
                            'humidity' => '%',
                            default => '',
                        },
                        'config' => [],
                    ]
                );
            }

            $nodes[] = $node;
        }

        return $nodes;
    }

    private function seedRecipes(): array
    {
        $this->command->info('Создание рецептов...');

        $recipes = [];

        $recipe1 = Recipe::firstOrCreate(
            ['name' => 'Lettuce Growing Recipe'],
            [
                'description' => 'Complete recipe for lettuce growing cycle',
            ]
        );

        // Фазы для рецепта 1
        $phases1 = [
            ['phase_index' => 0, 'name' => 'Germination', 'duration_hours' => 72, 'targets' => ['ph' => ['min' => 5.8, 'max' => 6.0], 'ec' => ['min' => 0.8, 'max' => 1.0]]],
            ['phase_index' => 1, 'name' => 'Vegetative', 'duration_hours' => 336, 'targets' => ['ph' => ['min' => 5.9, 'max' => 6.2], 'ec' => ['min' => 1.4, 'max' => 1.6]]],
            ['phase_index' => 2, 'name' => 'Maturation', 'duration_hours' => 720, 'targets' => ['ph' => ['min' => 6.0, 'max' => 6.5], 'ec' => ['min' => 1.6, 'max' => 1.8]]],
        ];

        foreach ($phases1 as $phaseData) {
            RecipePhase::firstOrCreate(
                [
                    'recipe_id' => $recipe1->id,
                    'phase_index' => $phaseData['phase_index'],
                ],
                $phaseData
            );
        }

        $recipes[] = $recipe1;

        $recipe2 = Recipe::firstOrCreate(
            ['name' => 'Tomato Growing Recipe'],
            [
                'description' => 'Complete recipe for tomato growing cycle',
            ]
        );

        // Фазы для рецепта 2
        $phases2 = [
            ['phase_index' => 0, 'name' => 'Seedling', 'duration_hours' => 336, 'targets' => ['ph' => ['min' => 6.0, 'max' => 6.3], 'ec' => ['min' => 1.2, 'max' => 1.5]]],
            ['phase_index' => 1, 'name' => 'Vegetative', 'duration_hours' => 720, 'targets' => ['ph' => ['min' => 6.2, 'max' => 6.5], 'ec' => ['min' => 1.8, 'max' => 2.2]]],
            ['phase_index' => 2, 'name' => 'Fruiting', 'duration_hours' => 1008, 'targets' => ['ph' => ['min' => 6.3, 'max' => 6.8], 'ec' => ['min' => 2.2, 'max' => 2.5]]],
        ];

        foreach ($phases2 as $phaseData) {
            RecipePhase::firstOrCreate(
                [
                    'recipe_id' => $recipe2->id,
                    'phase_index' => $phaseData['phase_index'],
                ],
                $phaseData
            );
        }

        $recipes[] = $recipe2;

        return $recipes;
    }

    private function seedRecipeInstances(array $zones, array $recipes): void
    {
        $this->command->info('Создание экземпляров рецептов...');

        foreach ($zones as $index => $zone) {
            if ($zone->status !== 'RUNNING') {
                continue;
            }

            $recipe = $recipes[$index % count($recipes)];
            $startedAt = now()->subDays(rand(5, 15));

            ZoneRecipeInstance::firstOrCreate(
                [
                    'zone_id' => $zone->id,
                ],
                [
                    'recipe_id' => $recipe->id,
                    'started_at' => $startedAt,
                    'current_phase_index' => rand(0, 2),
                ]
            );
        }
    }

    private function seedTelemetry(array $zones, array $nodes): void
    {
        $this->command->info('Создание телеметрии...');

        $metricTypes = ['ph', 'ec', 'temperature', 'humidity'];
        $now = now();

        // Создаем samples за последние 24 часа (каждые 5 минут)
        $samplesCount = 0;
        for ($hoursAgo = 23; $hoursAgo >= 0; $hoursAgo--) {
            $timestamp = $now->copy()->subHours($hoursAgo);

            for ($minute = 0; $minute < 60; $minute += 5) {
                $sampleTime = $timestamp->copy()->addMinutes($minute);

                foreach ($zones as $zone) {
                    foreach ($metricTypes as $metricType) {
                        // Генерируем реалистичные значения
                        $value = match ($metricType) {
                            'ph' => 6.0 + (rand(0, 20) / 10), // 6.0-8.0
                            'ec' => 1.0 + (rand(0, 25) / 10), // 1.0-3.5
                            'temperature' => 20.0 + (rand(0, 10) / 2), // 20.0-25.0
                            'humidity' => 60.0 + (rand(0, 30) / 2), // 60.0-75.0
                            default => rand(0, 100) / 10,
                        };

                        $randomNode = $nodes[array_rand($nodes)];
                        TelemetrySample::create([
                            'zone_id' => $zone->id,
                            'node_id' => $randomNode->id,
                            'channel' => $metricType,
                            'metric_type' => $metricType,
                            'value' => $value,
                            'ts' => $sampleTime,
                        ]);

                        $samplesCount++;
                    }
                }
            }
        }

        // Создаем последние значения (telemetry_last)
        // Primary key: (zone_id, metric_type) - только одна запись на зону и метрику
        foreach ($zones as $zone) {
            $zoneNodes = array_filter($nodes, fn ($n) => $n->zone_id === $zone->id);
            if (empty($zoneNodes)) {
                $zoneNodes = $nodes; // Fallback если нет узлов для зоны
            }

            foreach ($metricTypes as $metricType) {
                $randomNode = $zoneNodes[array_rand($zoneNodes)];
                TelemetryLast::updateOrCreate(
                    [
                        'zone_id' => $zone->id,
                        'metric_type' => $metricType,
                    ],
                    [
                        'node_id' => $randomNode->id,
                        'value' => match ($metricType) {
                            'ph' => 6.5,
                            'ec' => 1.8,
                            'temperature' => 22.5,
                            'humidity' => 65.0,
                            default => 0,
                        },
                        'updated_at' => now(),
                    ]
                );
            }
        }

        $this->command->info("Создано {$samplesCount} samples телеметрии");
    }

    private function seedCommands(array $zones, array $nodes): void
    {
        $this->command->info('Создание команд...');

        $commandTypes = ['DOSE', 'IRRIGATE', 'SET_LIGHT', 'SET_CLIMATE', 'READ_SENSOR'];
        $statuses = [Command::STATUS_QUEUED, Command::STATUS_SENT, Command::STATUS_DONE, Command::STATUS_FAILED];
        $statusWeights = [5, 20, 70, 5]; // Процентное распределение

        $commandsCount = 0;
        for ($daysAgo = 7; $daysAgo >= 0; $daysAgo--) {
            $dayStart = now()->subDays($daysAgo)->startOfDay();

            // 5-10 команд в день
            $commandsPerDay = rand(5, 10);

            for ($i = 0; $i < $commandsPerDay; $i++) {
                $zone = $zones[array_rand($zones)];
                $node = $nodes[array_rand($nodes)];
                $commandType = $commandTypes[array_rand($commandTypes)];

                // Выбираем статус по весам
                $rand = rand(1, 100);
                $cumulative = 0;
                $status = Command::STATUS_QUEUED;
                foreach ($statuses as $index => $stat) {
                    $cumulative += $statusWeights[$index];
                    if ($rand <= $cumulative) {
                        $status = $stat;
                        break;
                    }
                }

                $createdAt = $dayStart->copy()->addHours(rand(0, 23))->addMinutes(rand(0, 59));
                $sentAt = $status !== Command::STATUS_QUEUED ? $createdAt->copy()->addMinutes(rand(1, 5)) : null;
                $ackAt = in_array($status, [Command::STATUS_DONE, Command::STATUS_FAILED, Command::STATUS_TIMEOUT]) 
                    ? ($sentAt ? $sentAt->copy()->addMinutes(rand(1, 10)) : $createdAt->copy()->addMinutes(rand(1, 10))) 
                    : null;

                Command::create([
                    'zone_id' => $zone->id,
                    'node_id' => $node->id,
                    'cmd' => $commandType,
                    'status' => $status,
                    'params' => [
                        'action' => strtolower($commandType),
                    ],
                    'cmd_id' => Str::uuid()->toString(),
                    'created_at' => $createdAt,
                    'sent_at' => $sentAt,
                    'ack_at' => $ackAt,
                ]);

                $commandsCount++;
            }
        }

        $this->command->info("Создано {$commandsCount} команд");
    }

    private function seedAlerts(array $zones): void
    {
        $this->command->info('Создание алертов...');

        $alertTypes = ['pH_HIGH', 'pH_LOW', 'EC_HIGH', 'EC_LOW', 'TEMPERATURE_HIGH', 'TEMPERATURE_LOW', 'NODE_OFFLINE', 'PUMP_FAILURE'];
        $statuses = ['ACTIVE', 'RESOLVED'];

        $alertsCount = 0;
        for ($daysAgo = 30; $daysAgo >= 0; $daysAgo--) {
            $alertDate = now()->subDays($daysAgo);

            // 0-3 алерта в день
            $alertsPerDay = rand(0, 3);

            for ($i = 0; $i < $alertsPerDay; $i++) {
                $zone = $zones[array_rand($zones)];
                $alertType = $alertTypes[array_rand($alertTypes)];
                $status = $statuses[array_rand($statuses)];

                $resolvedAt = $status === 'RESOLVED' ? $alertDate->copy()->addHours(rand(1, 6)) : null;

                Alert::create([
                    'zone_id' => $zone->id,
                    'type' => $alertType,
                    'status' => strtoupper($status),
                    'details' => [
                        'message' => "Alert: {$alertType}",
                        'severity' => in_array($alertType, ['NODE_OFFLINE', 'PUMP_FAILURE']) ? 'critical' : 'warning',
                    ],
                    'created_at' => $alertDate,
                    'resolved_at' => $resolvedAt,
                ]);

                $alertsCount++;
            }
        }

        $this->command->info("Создано {$alertsCount} алертов");
    }

    private function seedZoneEvents(array $zones): void
    {
        $this->command->info('Создание событий зон...');

        $eventKinds = ['IRRIGATION_START', 'IRRIGATION_STOP', 'PHASE_CHANGE', 'ALERT_TRIGGERED', 'RECIPE_STARTED'];

        $eventsCount = 0;
        for ($daysAgo = 7; $daysAgo >= 0; $daysAgo--) {
            $dayStart = now()->subDays($daysAgo)->startOfDay();

            // 5-15 событий в день
            $eventsPerDay = rand(5, 15);

            for ($i = 0; $i < $eventsPerDay; $i++) {
                $zone = $zones[array_rand($zones)];
                $eventKind = $eventKinds[array_rand($eventKinds)];

                ZoneEvent::create([
                    'zone_id' => $zone->id,
                    'type' => $eventKind,
                    'details' => [
                        'message' => "Event: {$eventKind} in zone {$zone->name}",
                        'metadata' => [],
                    ],
                    'created_at' => $dayStart->copy()->addHours(rand(0, 23))->addMinutes(rand(0, 59)),
                ]);

                $eventsCount++;
            }
        }

        $this->command->info("Создано {$eventsCount} событий зон");
    }

    private function seedModelsAndSimulations(array $zones): void
    {
        $this->command->info('Создание моделей и симуляций...');

        foreach ($zones as $zone) {
            // Zone Model Params
            DB::table('zone_model_params')->insert([
                'zone_id' => $zone->id,
                'model_type' => 'growth_prediction',
                'params' => json_encode(['growth_rate' => rand(80, 120) / 100, 'efficiency' => rand(70, 95) / 100]),
                'calibrated_at' => now()->subDays(rand(1, 10)),
                'created_at' => now()->subDays(rand(1, 10)),
                'updated_at' => now()->subDays(rand(1, 10)),
            ]);

            // Zone Simulations
            DB::table('zone_simulations')->insert([
                'zone_id' => $zone->id,
                'scenario' => json_encode(['days' => 30, 'ph_target' => 6.5, 'ec_target' => 1.8]),
                'results' => json_encode(['predicted_ph' => 6.5, 'predicted_ec' => 1.8, 'predicted_yield' => rand(80, 120)]),
                'duration_hours' => 720,
                'step_minutes' => 60,
                'status' => 'completed',
                'created_at' => now()->subDays(rand(1, 5)),
                'updated_at' => now()->subDays(rand(1, 5)),
            ]);
        }
    }

    private function seedPredictions(array $zones): void
    {
        $this->command->info('Создание прогнозов AI...');

        $metricTypes = ['ph', 'ec', 'temperature'];

        foreach ($zones as $zone) {
            foreach ($metricTypes as $metricType) {
                DB::table('parameter_predictions')->insert([
                    'zone_id' => $zone->id,
                    'metric_type' => $metricType,
                    'predicted_value' => match ($metricType) {
                        'ph' => 6.5,
                        'ec' => 1.8,
                        'temperature' => 22.5,
                        default => 0,
                    },
                    'confidence' => rand(80, 100) / 100,
                    'horizon_minutes' => 60,
                    'predicted_at' => now()->subHours(rand(1, 24)),
                    'created_at' => now()->subHours(rand(1, 24)),
                    'updated_at' => now()->subHours(rand(1, 24)),
                ]);
            }
        }
    }

    private function seedHarvests(array $zones): void
    {
        $this->command->info('Создание урожаев...');

        foreach ($zones as $zone) {
            if ($zone->status === 'RUNNING') {
                DB::table('harvests')->insert([
                    'zone_id' => $zone->id,
                    'recipe_id' => $zone->recipeInstance?->recipe_id ?? null,
                    'harvest_date' => now()->subDays(rand(10, 30)),
                    'yield_weight_kg' => rand(50, 200) / 10,
                    'yield_count' => rand(100, 500),
                    'quality_score' => rand(7, 10) / 10,
                    'notes' => json_encode(['comment' => 'Test harvest data']),
                    'created_at' => now()->subDays(rand(10, 30)),
                    'updated_at' => now()->subDays(rand(10, 30)),
                ]);
            }
        }
    }

    private function seedFirmwareFiles(array $nodes): void
    {
        $this->command->info('Создание файлов прошивок...');

        $nodeTypes = ['sensor', 'actuator', 'controller'];
        foreach ($nodeTypes as $nodeType) {
            DB::table('firmware_files')->insert([
                'node_type' => $nodeType,
                'version' => '1.2.3',
                'file_path' => "/firmware/{$nodeType}/v1.2.3.bin",
                'checksum_sha256' => Str::random(64),
                'release_notes' => "Firmware update for {$nodeType} nodes",
                'created_at' => now()->subDays(rand(1, 10)),
            ]);
        }
    }

    private function seedLogs(array $zones, array $nodes): void
    {
        $this->command->info('Создание логов...');

        // System Logs
        for ($i = 0; $i < 50; $i++) {
            DB::table('system_logs')->insert([
                'level' => ['info', 'warning', 'error'][rand(0, 2)],
                'message' => 'System log entry '.($i + 1),
                'context' => json_encode([]),
                'created_at' => now()->subHours(rand(0, 72)),
            ]);
        }

        // Node Logs
        foreach ($nodes as $node) {
            for ($i = 0; $i < 20; $i++) {
                DB::table('node_logs')->insert([
                    'node_id' => $node->id,
                    'level' => ['info', 'warning', 'error'][rand(0, 2)],
                    'message' => "Node log entry for {$node->uid}",
                    'context' => json_encode([]),
                    'created_at' => now()->subHours(rand(0, 24)),
                ]);
            }
        }

        // AI Logs
        foreach ($zones as $zone) {
            for ($i = 0; $i < 10; $i++) {
                DB::table('ai_logs')->insert([
                    'zone_id' => $zone->id,
                    'action' => ['predict', 'recommend', 'explain', 'diagnostics'][rand(0, 3)],
                    'details' => json_encode(['message' => "AI log for zone {$zone->name}", 'data' => 'Test AI log data']),
                    'created_at' => now()->subHours(rand(0, 48)),
                ]);
            }
        }

        // Scheduler Logs
        for ($i = 0; $i < 30; $i++) {
            DB::table('scheduler_logs')->insert([
                'task_name' => ['recipe_phase', 'irrigation', 'dosing', 'light_control'][rand(0, 3)],
                'status' => ['success', 'failed'][rand(0, 1)],
                'details' => json_encode(['message' => 'Scheduler log entry '.($i + 1)]),
                'created_at' => now()->subHours(rand(0, 24)),
            ]);
        }
    }

    private function printStatistics(): void
    {
        $this->command->info('');
        $this->command->info('=== Статистика созданных данных ===');
        $this->command->info('Users: '.User::count());
        $this->command->info('Greenhouses: '.Greenhouse::count());
        $this->command->info('Zones: '.Zone::count());
        $this->command->info('Nodes: '.DeviceNode::count());
        $this->command->info('Node Channels: '.NodeChannel::count());
        $this->command->info('Recipes: '.Recipe::count());
        $this->command->info('Recipe Phases: '.RecipePhase::count());
        $this->command->info('Recipe Instances: '.ZoneRecipeInstance::count());
        $this->command->info('Telemetry Samples: '.number_format(TelemetrySample::count()));
        $this->command->info('Telemetry Last: '.TelemetryLast::count());
        $this->command->info('Commands: '.Command::count());
        $this->command->info('Alerts: '.Alert::count().' (Active: '.Alert::where('status', 'ACTIVE')->count().')');
        $this->command->info('Zone Events: '.ZoneEvent::count());
        $this->command->info('Zone Model Params: '.DB::table('zone_model_params')->count());
        $this->command->info('Zone Simulations: '.DB::table('zone_simulations')->count());
        $this->command->info('Parameter Predictions: '.DB::table('parameter_predictions')->count());
        $this->command->info('Harvests: '.DB::table('harvests')->count());
        $this->command->info('Firmware Files: '.DB::table('firmware_files')->count());
        $this->command->info('System Logs: '.DB::table('system_logs')->count());
        $this->command->info('Node Logs: '.DB::table('node_logs')->count());
        $this->command->info('AI Logs: '.DB::table('ai_logs')->count());
        $this->command->info('Scheduler Logs: '.DB::table('scheduler_logs')->count());
    }
}
