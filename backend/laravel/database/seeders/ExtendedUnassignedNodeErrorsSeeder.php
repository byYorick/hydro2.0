<?php

namespace Database\Seeders;

use App\Models\DeviceNode;
use App\Models\UnassignedNodeError;
use Illuminate\Database\Seeder;

/**
 * Сидер для ошибок непривязанных узлов
 */
class ExtendedUnassignedNodeErrorsSeeder extends Seeder
{
    public function run(): void
    {
        $this->command->info('=== Создание ошибок непривязанных узлов ===');

        $created = 0;

        // Создаем ошибки для непривязанных узлов
        $unassignedNodes = DeviceNode::whereNull('zone_id')->get();
        
        foreach ($unassignedNodes as $node) {
            $created += $this->seedErrorsForNode($node);
        }

        // Создаем несколько ошибок для узлов с hardware_id, но без zone_id
        $created += $this->seedRandomUnassignedErrors();

        $this->command->info("Создано ошибок: {$created}");
        $this->command->info("Всего ошибок: " . UnassignedNodeError::count());
    }

    private function seedErrorsForNode(DeviceNode $node): int
    {
        $created = 0;
        $errorCount = rand(0, 2);

        $errorTypes = [
            [
                'error_message' => 'Узел не может подключиться к MQTT брокеру',
                'error_code' => 'MQTT_CONNECTION_FAILED',
                'severity' => 'ERROR',
                'topic' => 'hydro/node/' . $node->hardware_id . '/error',
            ],
            [
                'error_message' => 'Ошибка чтения датчика pH',
                'error_code' => 'SENSOR_READ_ERROR',
                'severity' => 'WARNING',
                'topic' => 'hydro/node/' . $node->hardware_id . '/sensor/ph/error',
            ],
            [
                'error_message' => 'Низкий уровень сигнала WiFi',
                'error_code' => 'WIFI_LOW_SIGNAL',
                'severity' => 'WARNING',
                'topic' => 'hydro/node/' . $node->hardware_id . '/wifi/status',
            ],
        ];

        for ($i = 0; $i < $errorCount; $i++) {
            $errorType = $errorTypes[rand(0, count($errorTypes) - 1)];

            UnassignedNodeError::updateOrCreate(
                [
                    'hardware_id' => $node->hardware_id ?? 'HW-' . rand(1000, 9999),
                    'topic' => $errorType['topic'],
                ],
                [
                    'error_message' => $errorType['error_message'],
                    'error_code' => $errorType['error_code'],
                    'severity' => $errorType['severity'],
                    'last_payload' => [
                        'node_uid' => $node->uid,
                        'hardware_id' => $node->hardware_id,
                        'timestamp' => now()->toIso8601String(),
                    ],
                    'count' => rand(1, 10),
                    'first_seen_at' => now()->subDays(rand(1, 7)),
                    'last_seen_at' => now()->subHours(rand(0, 24)),
                    'node_id' => $node->id,
                ]
            );

            $created++;
        }

        return $created;
    }

    private function seedRandomUnassignedErrors(): int
    {
        $created = 0;
        $errorCount = rand(3, 8);

        $hardwareIds = ['HW-UNASSIGNED-001', 'HW-UNASSIGNED-002', 'HW-UNASSIGNED-003'];
        $errorTypes = [
            [
                'error_message' => 'Узел не зарегистрирован в системе',
                'error_code' => 'NODE_NOT_REGISTERED',
                'severity' => 'ERROR',
            ],
            [
                'error_message' => 'Отсутствует конфигурация зоны',
                'error_code' => 'ZONE_CONFIG_MISSING',
                'severity' => 'ERROR',
            ],
            [
                'error_message' => 'Ошибка валидации данных',
                'error_code' => 'VALIDATION_ERROR',
                'severity' => 'WARNING',
            ],
        ];

        for ($i = 0; $i < $errorCount; $i++) {
            $hardwareId = $hardwareIds[rand(0, count($hardwareIds) - 1)];
            $errorType = $errorTypes[rand(0, count($errorTypes) - 1)];
            $topic = 'hydro/temp/' . $hardwareId . '/error';

            UnassignedNodeError::updateOrCreate(
                [
                    'hardware_id' => $hardwareId,
                    'topic' => $topic,
                ],
                [
                    'error_message' => $errorType['error_message'],
                    'error_code' => $errorType['error_code'],
                    'severity' => $errorType['severity'],
                    'last_payload' => [
                        'hardware_id' => $hardwareId,
                        'timestamp' => now()->toIso8601String(),
                    ],
                    'count' => rand(1, 20),
                    'first_seen_at' => now()->subDays(rand(1, 14)),
                    'last_seen_at' => now()->subHours(rand(0, 48)),
                    'node_id' => null,
                ]
            );

            $created++;
        }

        return $created;
    }
}

