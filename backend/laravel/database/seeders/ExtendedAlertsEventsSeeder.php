<?php

namespace Database\Seeders;

use App\Models\Alert;
use App\Models\Zone;
use App\Models\ZoneEvent;
use Illuminate\Database\Seeder;

/**
 * Расширенный сидер для алертов и событий зон
 */
class ExtendedAlertsEventsSeeder extends Seeder
{
    public function run(): void
    {
        $this->command->info('=== Создание расширенных алертов и событий ===');

        $zones = Zone::all();
        if ($zones->isEmpty()) {
            $this->command->warn('Зоны не найдены.');
            return;
        }

        $alertsCreated = 0;
        $eventsCreated = 0;

        foreach ($zones as $zone) {
            $alertsCreated += $this->seedAlertsForZone($zone);
            $eventsCreated += $this->seedEventsForZone($zone);
        }

        $this->command->info("Создано алертов: " . number_format($alertsCreated));
        $this->command->info("Создано событий: " . number_format($eventsCreated));
        $this->command->info("Всего алертов: " . Alert::count());
        $this->command->info("Активных алертов: " . Alert::where('status', 'ACTIVE')->count());
        $this->command->info("Всего событий: " . ZoneEvent::count());
    }

    private function seedAlertsForZone(Zone $zone): int
    {
        $alertsCreated = 0;
        
        $daysBack = match ($zone->status) {
            'RUNNING' => 60,
            'PAUSED' => 30,
            'STOPPED' => 14,
            default => 14,
        };

        $alertTypes = [
            'pH_HIGH' => ['severity' => 'warning', 'source' => 'automation'],
            'pH_LOW' => ['severity' => 'warning', 'source' => 'automation'],
            'EC_HIGH' => ['severity' => 'warning', 'source' => 'automation'],
            'EC_LOW' => ['severity' => 'warning', 'source' => 'automation'],
            'TEMPERATURE_HIGH' => ['severity' => 'warning', 'source' => 'sensor'],
            'TEMPERATURE_LOW' => ['severity' => 'warning', 'source' => 'sensor'],
            'HUMIDITY_HIGH' => ['severity' => 'warning', 'source' => 'sensor'],
            'HUMIDITY_LOW' => ['severity' => 'warning', 'source' => 'sensor'],
            'NODE_OFFLINE' => ['severity' => 'critical', 'source' => 'system'],
            'PUMP_FAILURE' => ['severity' => 'critical', 'source' => 'hardware'],
            'SENSOR_ERROR' => ['severity' => 'error', 'source' => 'hardware'],
            'WATER_LEVEL_LOW' => ['severity' => 'warning', 'source' => 'sensor'],
            'NUTRIENT_LOW' => ['severity' => 'warning', 'source' => 'automation'],
            'LIGHT_FAILURE' => ['severity' => 'error', 'source' => 'hardware'],
        ];

        $statuses = ['ACTIVE' => 20, 'RESOLVED' => 80];

        $now = now();
        $startDate = $now->copy()->subDays($daysBack)->startOfDay();

        $currentDate = $startDate->copy();
        while ($currentDate->lt($now)) {
            // Количество алертов в день зависит от статуса зоны
            $alertsPerDay = match ($zone->status) {
                'RUNNING' => rand(0, 5),
                'PAUSED' => rand(0, 2),
                'STOPPED' => rand(0, 1),
                default => 0,
            };

            for ($i = 0; $i < $alertsPerDay; $i++) {
                $alertType = array_rand($alertTypes);
                $alertConfig = $alertTypes[$alertType];
                
                // Выбираем статус по весам
                $status = rand(1, 100) <= $statuses['ACTIVE'] ? 'ACTIVE' : 'RESOLVED';
                
                $createdAt = $currentDate->copy()->addHours(rand(0, 23))->addMinutes(rand(0, 59));
                $resolvedAt = $status === 'RESOLVED' 
                    ? $createdAt->copy()->addHours(rand(1, 48))
                    : null;

                Alert::create([
                    'zone_id' => $zone->id,
                    'source' => $alertConfig['source'],
                    'code' => strtoupper($alertType),
                    'type' => $alertType,
                    'details' => [
                        'message' => $this->getAlertMessage($alertType, $zone),
                        'severity' => $alertConfig['severity'],
                        'value' => $this->getAlertValue($alertType),
                        'threshold' => $this->getAlertThreshold($alertType),
                    ],
                    'status' => $status,
                    'created_at' => $createdAt,
                    'resolved_at' => $resolvedAt,
                ]);

                $alertsCreated++;
            }

            $currentDate->addDay();
        }

        return $alertsCreated;
    }

    private function seedEventsForZone(Zone $zone): int
    {
        $eventsCreated = 0;
        
        $daysBack = match ($zone->status) {
            'RUNNING' => 30,
            'PAUSED' => 14,
            'STOPPED' => 7,
            default => 7,
        };

        $eventTypes = [
            'IRRIGATION_START',
            'IRRIGATION_STOP',
            'PHASE_CHANGE',
            'ALERT_TRIGGERED',
            'RECIPE_STARTED',
            'RECIPE_COMPLETED',
            'HARVEST_STARTED',
            'HARVEST_COMPLETED',
            'NODE_CONNECTED',
            'NODE_DISCONNECTED',
            'SETTINGS_CHANGED',
            'MANUAL_INTERVENTION',
            'AUTO_MODE_ENABLED',
            'AUTO_MODE_DISABLED',
            'CALIBRATION_STARTED',
            'CALIBRATION_COMPLETED',
        ];

        $now = now();
        $startDate = $now->copy()->subDays($daysBack)->startOfDay();

        $currentDate = $startDate->copy();
        while ($currentDate->lt($now)) {
            // Количество событий в день зависит от статуса зоны
            $eventsPerDay = match ($zone->status) {
                'RUNNING' => rand(10, 30),
                'PAUSED' => rand(3, 10),
                'STOPPED' => rand(1, 5),
                default => 5,
            };

            for ($i = 0; $i < $eventsPerDay; $i++) {
                $eventType = $eventTypes[array_rand($eventTypes)];

                ZoneEvent::create([
                    'zone_id' => $zone->id,
                    'type' => $eventType,
                    'details' => [
                        'message' => $this->getEventMessage($eventType, $zone),
                        'metadata' => $this->getEventMetadata($eventType),
                    ],
                    'created_at' => $currentDate->copy()->addHours(rand(0, 23))->addMinutes(rand(0, 59)),
                ]);

                $eventsCreated++;
            }

            $currentDate->addDay();
        }

        return $eventsCreated;
    }

    private function getAlertMessage(string $alertType, Zone $zone): string
    {
        return match ($alertType) {
            'pH_HIGH' => "pH в зоне {$zone->name} превысил допустимое значение",
            'pH_LOW' => "pH в зоне {$zone->name} ниже допустимого значения",
            'EC_HIGH' => "EC в зоне {$zone->name} превысил допустимое значение",
            'EC_LOW' => "EC в зоне {$zone->name} ниже допустимого значения",
            'TEMPERATURE_HIGH' => "Температура в зоне {$zone->name} слишком высокая",
            'TEMPERATURE_LOW' => "Температура в зоне {$zone->name} слишком низкая",
            'NODE_OFFLINE' => "Узел в зоне {$zone->name} не отвечает",
            'PUMP_FAILURE' => "Ошибка насоса в зоне {$zone->name}",
            default => "Алерт {$alertType} в зоне {$zone->name}",
        };
    }

    private function getAlertValue(string $alertType): ?float
    {
        return match ($alertType) {
            'pH_HIGH' => rand(70, 90) / 10,
            'pH_LOW' => rand(40, 55) / 10,
            'EC_HIGH' => rand(30, 40) / 10,
            'EC_LOW' => rand(5, 10) / 10,
            'TEMPERATURE_HIGH' => rand(28, 35),
            'TEMPERATURE_LOW' => rand(10, 15),
            default => null,
        };
    }

    private function getAlertThreshold(string $alertType): ?float
    {
        return match ($alertType) {
            'pH_HIGH' => 6.5,
            'pH_LOW' => 5.5,
            'EC_HIGH' => 2.5,
            'EC_LOW' => 1.0,
            'TEMPERATURE_HIGH' => 26,
            'TEMPERATURE_LOW' => 18,
            default => null,
        };
    }

    private function getEventMessage(string $eventType, Zone $zone): string
    {
        return match ($eventType) {
            'IRRIGATION_START' => "Полив начат в зоне {$zone->name}",
            'IRRIGATION_STOP' => "Полив остановлен в зоне {$zone->name}",
            'PHASE_CHANGE' => "Изменение фазы в зоне {$zone->name}",
            'RECIPE_STARTED' => "Рецепт запущен в зоне {$zone->name}",
            'RECIPE_COMPLETED' => "Рецепт завершен в зоне {$zone->name}",
            default => "Событие {$eventType} в зоне {$zone->name}",
        };
    }

    private function getEventMetadata(string $eventType): array
    {
        return match ($eventType) {
            'IRRIGATION_START', 'IRRIGATION_STOP' => [
                'duration' => rand(5, 30),
                'pump_id' => rand(1, 3),
            ],
            'PHASE_CHANGE' => [
                'from_phase' => rand(0, 2),
                'to_phase' => rand(1, 3),
            ],
            'RECIPE_STARTED' => [
                'recipe_id' => rand(1, 5),
            ],
            default => [],
        };
    }
}

