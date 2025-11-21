<?php

namespace Database\Seeders;

use Illuminate\Database\Seeder;
use App\Models\Zone;
use App\Models\DeviceNode;
use App\Models\Alert;
use App\Models\ZoneEvent;
use Carbon\Carbon;

/**
 * Seeder для создания дополнительных данных для демонстрации мониторинга
 * Создает события и алерты для визуализации в Grafana dashboards
 */
class MonitoringDataSeeder extends Seeder
{
    public function run(): void
    {
        $zones = Zone::with('nodes')->get();
        
        if ($zones->isEmpty()) {
            $this->command->warn('Нет зон для создания данных мониторинга. Сначала запустите DemoDataSeeder.');
            return;
        }

        $this->command->info('Создание данных для мониторинга...');

        // Создаем события для каждой зоны за последние 7 дней
        foreach ($zones as $zone) {
            $this->command->info("Создание событий для зоны: {$zone->name}...");
            
            // События за последние 7 дней
            $eventTypes = [
                'PH_CORRECTION' => ['dose_ml' => 0.5, 'before' => 6.2, 'after' => 5.9],
                'EC_CORRECTION' => ['dose_ml' => 1.0, 'before' => 1.3, 'after' => 1.5],
                'IRRIGATION_START' => ['duration_sec' => 8, 'flow_rate' => 2.1],
                'IRRIGATION_STOP' => ['duration_sec' => 8, 'total_ml' => 16.8],
                'PHASE_TRANSITION' => ['from_phase' => 0, 'to_phase' => 1, 'phase_name' => 'growth'],
                'LIGHT_ON' => ['intensity' => 300, 'duration_min' => 60],
                'LIGHT_OFF' => ['intensity' => 0],
            ];

            // Создаем по 2-3 события каждого типа за последние 7 дней
            foreach ($eventTypes as $eventType => $defaultDetails) {
                for ($i = 0; $i < rand(2, 3); $i++) {
                    $daysAgo = rand(0, 7);
                    $hoursAgo = rand(0, 23);
                    
                    ZoneEvent::create([
                        'zone_id' => $zone->id,
                        'type' => $eventType,
                        'details' => array_merge($defaultDetails, [
                            'timestamp' => Carbon::now()->subDays($daysAgo)->subHours($hoursAgo)->toIso8601String(),
                        ]),
                        'created_at' => Carbon::now()->subDays($daysAgo)->subHours($hoursAgo),
                    ]);
                }
            }
        }

        // Создаем дополнительные алерты для демонстрации
        $this->command->info('Создание дополнительных алертов...');
        
        $alertTypes = [
            'PH_HIGH' => ['threshold' => 6.0, 'current' => 6.3],
            'PH_LOW' => ['threshold' => 5.5, 'current' => 5.2],
            'EC_HIGH' => ['threshold' => 1.8, 'current' => 2.0],
            'EC_LOW' => ['threshold' => 1.2, 'current' => 1.0],
            'TEMP_HIGH' => ['threshold' => 25, 'current' => 27],
            'TEMP_LOW' => ['threshold' => 18, 'current' => 16],
            'HUMIDITY_HIGH' => ['threshold' => 70, 'current' => 75],
            'HUMIDITY_LOW' => ['threshold' => 50, 'current' => 45],
            'WATER_LEVEL_LOW' => ['threshold' => 20, 'current' => 15],
            'NO_FLOW' => ['expected_flow' => 2.0, 'actual_flow' => 0.0],
            'NODE_OFFLINE' => ['node_uid' => 'nd-temp-001', 'offline_since' => Carbon::now()->subHours(2)->toIso8601String()],
        ];

        foreach ($zones as $zone) {
            // Создаем несколько активных алертов
            $activeAlerts = rand(1, 3);
            for ($i = 0; $i < $activeAlerts; $i++) {
                $alertType = array_rand($alertTypes);
                $details = $alertTypes[$alertType];
                
                // Проверяем, нет ли уже такого алерта
                if (Alert::where('zone_id', $zone->id)
                    ->where('type', strtolower($alertType))
                    ->where('status', 'active')
                    ->count() === 0) {
                    
                    Alert::create([
                        'zone_id' => $zone->id,
                        'type' => strtolower($alertType),
                        'status' => 'active',
                        'details' => array_merge($details, [
                            'message' => $this->getAlertMessage($alertType, $details),
                        ]),
                        'created_at' => Carbon::now()->subHours(rand(1, 24)),
                    ]);
                }
            }

            // Создаем несколько решенных алертов за последние 7 дней
            $resolvedAlerts = rand(2, 5);
            for ($i = 0; $i < $resolvedAlerts; $i++) {
                $alertType = array_rand($alertTypes);
                $details = $alertTypes[$alertType];
                $daysAgo = rand(1, 7);
                $resolvedHoursAgo = rand(1, 12);
                
                Alert::create([
                    'zone_id' => $zone->id,
                    'type' => strtolower($alertType),
                    'status' => 'resolved',
                    'details' => array_merge($details, [
                        'message' => $this->getAlertMessage($alertType, $details),
                    ]),
                    'created_at' => Carbon::now()->subDays($daysAgo),
                    'resolved_at' => Carbon::now()->subDays($daysAgo)->subHours($resolvedHoursAgo),
                ]);
            }
        }

        $totalEvents = ZoneEvent::count();
        $totalAlerts = Alert::count();
        $activeAlerts = Alert::where('status', 'active')->count();
        
        $this->command->info("Данные для мониторинга созданы успешно!");
        $this->command->info("- Всего событий: {$totalEvents}");
        $this->command->info("- Всего алертов: {$totalAlerts}");
        $this->command->info("- Активных алертов: {$activeAlerts}");
    }

    private function getAlertMessage(string $alertType, array $details): string
    {
        return match (strtoupper($alertType)) {
            'PH_HIGH' => "pH level too high: {$details['current']} (threshold: {$details['threshold']})",
            'PH_LOW' => "pH level too low: {$details['current']} (threshold: {$details['threshold']})",
            'EC_HIGH' => "EC level too high: {$details['current']} (threshold: {$details['threshold']})",
            'EC_LOW' => "EC level too low: {$details['current']} (threshold: {$details['threshold']})",
            'TEMP_HIGH' => "Temperature too high: {$details['current']}°C (threshold: {$details['threshold']}°C)",
            'TEMP_LOW' => "Temperature too low: {$details['current']}°C (threshold: {$details['threshold']}°C)",
            'HUMIDITY_HIGH' => "Humidity too high: {$details['current']}% (threshold: {$details['threshold']}%)",
            'HUMIDITY_LOW' => "Humidity too low: {$details['current']}% (threshold: {$details['threshold']}%)",
            'WATER_LEVEL_LOW' => "Water level too low: {$details['current']}% (threshold: {$details['threshold']}%)",
            'NO_FLOW' => "No water flow detected (expected: {$details['expected_flow']} L/min)",
            'NODE_OFFLINE' => "Node {$details['node_uid']} is offline since {$details['offline_since']}",
            default => "Alert: {$alertType}",
        };
    }
}

