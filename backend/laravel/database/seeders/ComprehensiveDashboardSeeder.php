<?php

namespace Database\Seeders;

use App\Models\Alert;
use App\Models\Command;
use App\Models\DeviceNode;
use App\Models\Sensor;
use App\Models\TelemetryLast;
use App\Models\Zone;
use App\Models\ZoneEvent;
use Carbon\Carbon;
use Illuminate\Database\Seeder;
use Illuminate\Support\Str;

/**
 * Комплексный сидер для заполнения всех таблиц для проверки всех Grafana dashboards
 *
 * Dashboards:
 * - Alerts Dashboard: alerts
 * - Automation Engine Service: zones, commands
 * - History Logger Service: telemetry (через TelemetrySeeder)
 * - Node Status: nodes (статусы online/offline)
 * - System Overview: все таблицы
 * - Zone Telemetry: zones, telemetry
 * - Commands & Automation: commands
 */
class ComprehensiveDashboardSeeder extends Seeder
{
    public function run(): void
    {
        $zones = Zone::with(['nodes.channels'])->get();

        if ($zones->isEmpty()) {
            $this->command->warn('Нет зон. Сначала запустите DemoDataSeeder.');

            return;
        }

        $this->command->info('=== Заполнение данных для всех Grafana dashboards ===');

        // 1. Обновление статусов узлов для Node Status Dashboard
        $this->seedNodeStatuses($zones);

        // 2. Создание команд для Automation Engine и Commands & Automation dashboards
        $this->seedCommands($zones);

        // 3. Расширенное заполнение алертов для Alerts Dashboard
        $this->seedAlerts($zones);

        // 4. Создание событий для Zone Telemetry Dashboard
        $this->seedZoneEvents($zones);

        // 5. Обновление telemetry_last для History Logger Dashboard
        $this->updateTelemetryLast($zones);

        $this->command->info('=== Итоговая статистика ===');
        $this->printStatistics();
    }

    /**
     * Обновление статусов узлов для Node Status Dashboard
     */
    private function seedNodeStatuses($zones): void
    {
        $this->command->info('1. Обновление статусов узлов...');

        foreach ($zones as $zone) {
            foreach ($zone->nodes as $index => $node) {
                // Смешиваем online/offline статусы для реалистичности
                $status = ($index % 3 === 0) ? 'offline' : 'online';

                // Обновляем last_seen_at в зависимости от статуса
                $lastSeen = $status === 'online'
                    ? Carbon::now()->subMinutes(rand(1, 30))
                    : Carbon::now()->subHours(rand(2, 24));

                $node->update([
                    'status' => $status,
                    'last_seen_at' => $lastSeen,
                    'last_heartbeat_at' => $status === 'online' ? $lastSeen : null,
                    'updated_at' => Carbon::now(),
                ]);

                // Добавляем метрики для online узлов
                if ($status === 'online') {
                    $node->update([
                        'uptime_seconds' => rand(86400, 2592000), // 1-30 дней
                        'free_heap_bytes' => rand(50000, 200000),
                        'rssi' => rand(-70, -30),
                    ]);
                }
            }
        }

        $onlineCount = DeviceNode::where('status', 'online')->count();
        $offlineCount = DeviceNode::where('status', 'offline')->count();
        $this->command->info("   - Online узлов: {$onlineCount}");
        $this->command->info("   - Offline узлов: {$offlineCount}");
    }

    /**
     * Создание команд для Automation Engine и Commands & Automation dashboards
     */
    private function seedCommands($zones): void
    {
        $this->command->info('2. Создание команд...');

        $commandTemplates = [
            ['cmd' => 'DOSE', 'params' => ['ml' => 0.5, 'channel' => 'pump_acid']],
            ['cmd' => 'DOSE', 'params' => ['ml' => 1.0, 'channel' => 'pump_base']],
            ['cmd' => 'DOSE', 'params' => ['ml' => 2.0, 'channel' => 'pump_a']],
            ['cmd' => 'DOSE', 'params' => ['ml' => 2.0, 'channel' => 'pump_b']],
            ['cmd' => 'DOSE', 'params' => ['ml' => 2.0, 'channel' => 'pump_c']],
            ['cmd' => 'DOSE', 'params' => ['ml' => 1.0, 'channel' => 'pump_d']],
            ['cmd' => 'IRRIGATE', 'params' => ['duration_sec' => 8, 'flow_rate' => 2.0]],
            ['cmd' => 'SET_LIGHT', 'params' => ['intensity' => 300, 'duration_min' => 60]],
            ['cmd' => 'SET_CLIMATE', 'params' => ['temp' => 22.0, 'humidity' => 60]],
            ['cmd' => 'READ_SENSOR', 'params' => ['metric' => 'PH']],
            ['cmd' => 'READ_SENSOR', 'params' => ['metric' => 'EC']],
        ];

        $statuses = [
            Command::STATUS_QUEUED,
            Command::STATUS_SENT,
            Command::STATUS_ACK,
            Command::STATUS_DONE,
            Command::STATUS_NO_EFFECT,
            Command::STATUS_ERROR,
            Command::STATUS_INVALID,
            Command::STATUS_BUSY,
            Command::STATUS_TIMEOUT,
            Command::STATUS_SEND_FAILED,
        ];
        $statusWeights = [
            Command::STATUS_QUEUED => 5,
            Command::STATUS_SENT => 20,
            Command::STATUS_ACK => 10,
            Command::STATUS_DONE => 45,
            Command::STATUS_NO_EFFECT => 5,
            Command::STATUS_ERROR => 5,
            Command::STATUS_INVALID => 3,
            Command::STATUS_BUSY => 2,
            Command::STATUS_TIMEOUT => 3,
            Command::STATUS_SEND_FAILED => 2,
        ]; // Процентное распределение

        $totalCommands = 0;

        foreach ($zones as $zone) {
            $nodes = $zone->nodes;
            if ($nodes->isEmpty()) {
                continue;
            }

            // Создаем команды за последние 7 дней
            for ($day = 0; $day < 7; $day++) {
                $commandsPerDay = rand(10, 30); // 10-30 команд в день

                for ($i = 0; $i < $commandsPerDay; $i++) {
                    $node = $nodes->random();
                    $commandTemplate = $commandTemplates[array_rand($commandTemplates)];
                    $cmdType = $commandTemplate['cmd'];
                    $params = $commandTemplate['params'];

                    // Выбираем статус с учетом весов
                    $status = $this->weightedRandom($statusWeights);

                    $createdAt = Carbon::now()->subDays($day)->subHours(rand(0, 23))->subMinutes(rand(0, 59));

                    // Временные метки в зависимости от статуса
                    $sentAt = null;
                    $ackAt = null;
                    $failedAt = null;

                    if (in_array($status, [
                        Command::STATUS_SENT,
                        Command::STATUS_ACK,
                        Command::STATUS_DONE,
                        Command::STATUS_NO_EFFECT,
                        Command::STATUS_ERROR,
                        Command::STATUS_INVALID,
                        Command::STATUS_BUSY,
                        Command::STATUS_TIMEOUT,
                    ], true)) {
                        $sentAt = $createdAt->copy()->addSeconds(rand(1, 5));
                    }

                    if (in_array($status, [Command::STATUS_ACK, Command::STATUS_DONE, Command::STATUS_NO_EFFECT], true)) {
                        $ackAt = $sentAt ? $sentAt->copy()->addSeconds(rand(1, 10)) : $createdAt->copy()->addSeconds(rand(1, 10));
                    } elseif (in_array($status, [
                        Command::STATUS_ERROR,
                        Command::STATUS_INVALID,
                        Command::STATUS_BUSY,
                        Command::STATUS_TIMEOUT,
                        Command::STATUS_SEND_FAILED,
                    ], true)) {
                        $failedAt = $sentAt ? $sentAt->copy()->addSeconds(rand(5, 30)) : $createdAt->copy()->addSeconds(rand(5, 30));
                    }

                    // Выбираем канал из узла
                    $channel = null;
                    if ($node->channels->isNotEmpty()) {
                        $actuatorChannels = $node->channels->where('type', 'actuator');
                        if ($actuatorChannels->isNotEmpty()) {
                            $channel = $actuatorChannels->random()->channel;
                        } else {
                            $channel = $node->channels->random()->channel;
                        }
                    }

                    Command::create([
                        'zone_id' => $zone->id,
                        'node_id' => $node->id,
                        'channel' => $channel,
                        'cmd' => $cmdType,
                        'params' => $params,
                        'status' => $status,
                        'cmd_id' => Str::uuid()->toString(),
                        'created_at' => $createdAt,
                        'sent_at' => $sentAt,
                        'ack_at' => $ackAt,
                        'failed_at' => $failedAt,
                        'updated_at' => $createdAt,
                    ]);

                    $totalCommands++;
                }
            }
        }

        $this->command->info("   - Создано команд: {$totalCommands}");
        $this->printCommandStatistics();
    }

    /**
     * Расширенное заполнение алертов для Alerts Dashboard
     */
    private function seedAlerts($zones): void
    {
        $this->command->info('3. Расширенное заполнение алертов...');

        $alertTypes = [
            'ph_high' => ['threshold' => 6.0, 'current' => 6.3, 'severity' => 'warning'],
            'ph_low' => ['threshold' => 5.5, 'current' => 5.2, 'severity' => 'warning'],
            'ec_high' => ['threshold' => 1.8, 'current' => 2.0, 'severity' => 'warning'],
            'ec_low' => ['threshold' => 1.2, 'current' => 1.0, 'severity' => 'critical'],
            'temp_high' => ['threshold' => 25, 'current' => 27, 'severity' => 'warning'],
            'temp_low' => ['threshold' => 18, 'current' => 16, 'severity' => 'critical'],
            'humidity_high' => ['threshold' => 70, 'current' => 75, 'severity' => 'warning'],
            'humidity_low' => ['threshold' => 50, 'current' => 45, 'severity' => 'warning'],
            'water_level_low' => ['threshold' => 20, 'current' => 15, 'severity' => 'critical'],
            'no_flow' => ['expected_flow' => 2.0, 'actual_flow' => 0.0, 'severity' => 'critical'],
            'node_offline' => ['node_uid' => 'nd-temp-001', 'severity' => 'warning'],
            'sensor_error' => ['sensor_type' => 'PH', 'error_code' => 'E001', 'severity' => 'critical'],
            'pump_failure' => ['pump_channel' => 'pump_acid', 'severity' => 'critical'],
            'config_mismatch' => ['expected_version' => '1.2.3', 'actual_version' => '1.2.2', 'severity' => 'warning'],
        ];

        $totalAlerts = 0;

        foreach ($zones as $zone) {
            // Активные алерты (1-5 на зону)
            $activeCount = rand(1, 5);
            for ($i = 0; $i < $activeCount; $i++) {
                $alertType = array_rand($alertTypes);
                $details = $alertTypes[$alertType];

                Alert::create([
                    'zone_id' => $zone->id,
                    'type' => $alertType,
                    'status' => 'active',
                    'details' => array_merge($details, [
                        'message' => $this->getAlertMessage($alertType, $details),
                        'zone_name' => $zone->name,
                    ]),
                    'created_at' => Carbon::now()->subHours(rand(1, 48)),
                ]);
                $totalAlerts++;
            }

            // Решенные алерты за последние 7 дней (5-15 на зону)
            $resolvedCount = rand(5, 15);
            for ($i = 0; $i < $resolvedCount; $i++) {
                $alertType = array_rand($alertTypes);
                $details = $alertTypes[$alertType];
                $daysAgo = rand(1, 7);
                $resolvedHoursAgo = rand(1, 24);

                Alert::create([
                    'zone_id' => $zone->id,
                    'type' => $alertType,
                    'status' => 'resolved',
                    'details' => array_merge($details, [
                        'message' => $this->getAlertMessage($alertType, $details),
                        'zone_name' => $zone->name,
                    ]),
                    'created_at' => Carbon::now()->subDays($daysAgo),
                    'resolved_at' => Carbon::now()->subDays($daysAgo)->subHours($resolvedHoursAgo),
                ]);
                $totalAlerts++;
            }
        }

        $activeAlerts = Alert::where('status', 'active')->count();
        $resolvedAlerts = Alert::where('status', 'resolved')->count();
        $this->command->info("   - Всего алертов: {$totalAlerts}");
        $this->command->info("   - Активных: {$activeAlerts}");
        $this->command->info("   - Решенных: {$resolvedAlerts}");
    }

    /**
     * Создание событий для Zone Telemetry Dashboard
     */
    private function seedZoneEvents($zones): void
    {
        $this->command->info('4. Создание событий зон...');

        $eventTypes = [
            'PH_CORRECTION' => ['dose_ml' => 0.5, 'before' => 6.2, 'after' => 5.9, 'node_id' => null],
            'EC_CORRECTION' => ['dose_ml' => 1.0, 'before' => 1.3, 'after' => 1.5, 'node_id' => null],
            'IRRIGATION_START' => ['duration_sec' => 8, 'flow_rate' => 2.1, 'node_id' => null],
            'IRRIGATION_STOP' => ['duration_sec' => 8, 'total_ml' => 16.8, 'node_id' => null],
            'PHASE_TRANSITION' => ['from_phase' => 0, 'to_phase' => 1, 'phase_name' => 'growth'],
            'LIGHT_ON' => ['intensity' => 300, 'duration_min' => 60, 'node_id' => null],
            'LIGHT_OFF' => ['intensity' => 0, 'node_id' => null],
            'CLIMATE_ADJUSTMENT' => ['temp_before' => 23.0, 'temp_after' => 22.0, 'humidity_before' => 65, 'humidity_after' => 60],
            'NODE_ONLINE' => ['node_uid' => null, 'uptime_seconds' => 86400],
            'NODE_OFFLINE' => ['node_uid' => null, 'offline_since' => null],
        ];

        $totalEvents = 0;

        foreach ($zones as $zone) {
            $nodes = $zone->nodes;

            // Создаем события за последние 7 дней
            for ($day = 0; $day < 7; $day++) {
                $eventsPerDay = rand(15, 40); // 15-40 событий в день

                for ($i = 0; $i < $eventsPerDay; $i++) {
                    $eventType = array_rand($eventTypes);
                    $details = $eventTypes[$eventType];

                    // Добавляем node_id если есть узлы
                    if (isset($details['node_id']) && $nodes->isNotEmpty()) {
                        $randomNode = $nodes->random();
                        $details['node_id'] = $randomNode->id;
                        if (isset($details['node_uid'])) {
                            $details['node_uid'] = $randomNode->uid;
                        }
                    }

                    $createdAt = Carbon::now()->subDays($day)->subHours(rand(0, 23))->subMinutes(rand(0, 59));

                    ZoneEvent::create([
                        'zone_id' => $zone->id,
                        'type' => $eventType,
                        'details' => array_merge($details, [
                            'timestamp' => $createdAt->toIso8601String(),
                        ]),
                        'created_at' => $createdAt,
                    ]);

                    $totalEvents++;
                }
            }
        }

        $this->command->info("   - Создано событий: {$totalEvents}");
    }

    /**
     * Обновление telemetry_last для History Logger Dashboard
     */
    private function updateTelemetryLast($zones): void
    {
        $this->command->info('5. Обновление последних значений телеметрии...');

        $metricTypes = ['PH', 'EC', 'TEMPERATURE', 'HUMIDITY', 'WATER_LEVEL', 'FLOW_RATE'];
        $baseValues = [
            'PH' => 5.8,
            'EC' => 1.5,
            'TEMPERATURE' => 22.0,
            'HUMIDITY' => 60.0,
            'WATER_LEVEL' => 50.0,
            'FLOW_RATE' => 2.0,
        ];

        $updated = 0;

        foreach ($zones as $zone) {
            foreach ($zone->nodes as $node) {
                foreach ($metricTypes as $metricType) {
                    $sensorType = $this->sensorTypeFromMetric($metricType);
                    $baseValue = $baseValues[$metricType] ?? 0.0;
                    $variation = $this->getVariationForMetric($metricType);
                    $value = $baseValue + (rand(-100, 100) / 100) * $variation;

                    $sensor = Sensor::firstOrCreate(
                        [
                            'greenhouse_id' => $zone->greenhouse_id,
                            'zone_id' => $zone->id,
                            'node_id' => $node->id,
                            'scope' => 'inside',
                            'type' => $sensorType,
                            'label' => $this->buildSensorLabel($metricType, $sensorType),
                        ],
                        [
                            'unit' => null,
                            'specs' => [
                                'metric' => $metricType,
                                'channel' => 'default',
                            ],
                            'is_active' => true,
                        ]
                    );

                    TelemetryLast::updateOrCreate(
                        [
                            'sensor_id' => $sensor->id,
                        ],
                        [
                            'last_value' => round($value, 2),
                            'last_ts' => Carbon::now()->subMinutes(rand(1, 30)),
                            'last_quality' => 'GOOD',
                        ]
                    );
                    $updated++;
                }
            }
        }

        $this->command->info("   - Обновлено записей: {$updated}");
    }

    /**
     * Вывод статистики команд
     */
    private function printCommandStatistics(): void
    {
        $stats = [
            'QUEUED' => Command::where('status', Command::STATUS_QUEUED)->count(),
            'SENT' => Command::where('status', Command::STATUS_SENT)->count(),
            'ACK' => Command::where('status', Command::STATUS_ACK)->count(),
            'DONE' => Command::where('status', Command::STATUS_DONE)->count(),
            'NO_EFFECT' => Command::where('status', Command::STATUS_NO_EFFECT)->count(),
            'ERROR' => Command::where('status', Command::STATUS_ERROR)->count(),
            'INVALID' => Command::where('status', Command::STATUS_INVALID)->count(),
            'BUSY' => Command::where('status', Command::STATUS_BUSY)->count(),
            'TIMEOUT' => Command::where('status', Command::STATUS_TIMEOUT)->count(),
            'SEND_FAILED' => Command::where('status', Command::STATUS_SEND_FAILED)->count(),
        ];

        $this->command->info('   - Статусы команд:');
        foreach ($stats as $status => $count) {
            $this->command->info("     * {$status}: {$count}");
        }
    }

    /**
     * Вывод общей статистики
     */
    private function printStatistics(): void
    {
        $stats = [
            'Зоны' => Zone::count(),
            'Узлы' => DeviceNode::count(),
            'Узлы (online)' => DeviceNode::where('status', 'online')->count(),
            'Узлы (offline)' => DeviceNode::where('status', 'offline')->count(),
            'Команды' => Command::count(),
            'Алерты (всего)' => Alert::count(),
            'Алерты (активные)' => Alert::where('status', 'active')->count(),
            'События' => ZoneEvent::count(),
            'Телеметрия (last)' => TelemetryLast::count(),
        ];

        foreach ($stats as $label => $count) {
            $this->command->info("   {$label}: {$count}");
        }
    }

    /**
     * Взвешенный случайный выбор
     */
    private function weightedRandom(array $weights): string
    {
        $total = array_sum($weights);
        $random = rand(1, $total);
        $current = 0;

        foreach ($weights as $key => $weight) {
            $current += $weight;
            if ($random <= $current) {
                return $key;
            }
        }

        return array_key_first($weights);
    }

    /**
     * Получить сообщение для алерта
     */
    private function getAlertMessage(string $alertType, array $details): string
    {
        return match (strtolower($alertType)) {
            'ph_high' => "pH level too high: {$details['current']} (threshold: {$details['threshold']})",
            'ph_low' => "pH level too low: {$details['current']} (threshold: {$details['threshold']})",
            'ec_high' => "EC level too high: {$details['current']} (threshold: {$details['threshold']})",
            'ec_low' => "EC level too low: {$details['current']} (threshold: {$details['threshold']})",
            'temp_high' => "Temperature too high: {$details['current']}°C (threshold: {$details['threshold']}°C)",
            'temp_low' => "Temperature too low: {$details['current']}°C (threshold: {$details['threshold']}°C)",
            'humidity_high' => "Humidity too high: {$details['current']}% (threshold: {$details['threshold']}%)",
            'humidity_low' => "Humidity too low: {$details['current']}% (threshold: {$details['threshold']}%)",
            'water_level_low' => "Water level too low: {$details['current']}% (threshold: {$details['threshold']}%)",
            'no_flow' => "No water flow detected (expected: {$details['expected_flow']} L/min)",
            'node_offline' => "Node {$details['node_uid']} is offline",
            'sensor_error' => "Sensor error: {$details['sensor_type']} - {$details['error_code']}",
            'pump_failure' => "Pump failure: {$details['pump_channel']}",
            'config_mismatch' => "Config mismatch: expected {$details['expected_version']}, got {$details['actual_version']}",
            default => "Alert: {$alertType}",
        };
    }

    /**
     * Получить вариацию для метрики
     */
    private function getVariationForMetric(string $metric): float
    {
        return match (strtoupper($metric)) {
            'PH', 'PH_VALUE' => 0.3,
            'EC', 'EC_VALUE' => 0.2,
            'TEMPERATURE' => 3.0,
            'HUMIDITY' => 10.0,
            'WATER_LEVEL' => 15.0,
            'FLOW_RATE' => 0.5,
            default => 1.0,
        };
    }

    private function sensorTypeFromMetric(string $metric): string
    {
        $metric = strtoupper($metric);

        return match ($metric) {
            'PH' => 'PH',
            'EC' => 'EC',
            'TEMPERATURE' => 'TEMPERATURE',
            'HUMIDITY' => 'HUMIDITY',
            'WATER_LEVEL' => 'WATER_LEVEL',
            'FLOW_RATE' => 'FLOW_RATE',
            default => 'OTHER',
        };
    }

    private function buildSensorLabel(string $metricType, string $sensorType): string
    {
        $base = str_replace('_', ' ', strtolower($metricType));
        $base = trim($base) ?: strtolower($sensorType);

        return ucfirst($base);
    }
}
