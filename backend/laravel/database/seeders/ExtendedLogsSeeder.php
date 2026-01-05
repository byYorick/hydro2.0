<?php

namespace Database\Seeders;

use App\Models\AiLog;
use App\Models\DeviceNode;
use App\Models\NodeLog;
use App\Models\SchedulerLog;
use App\Models\SystemLog;
use App\Models\Zone;
use Illuminate\Database\Seeder;
use Illuminate\Support\Facades\DB;

/**
 * Расширенный сидер для логов всех типов
 */
class ExtendedLogsSeeder extends Seeder
{
    public function run(): void
    {
        $this->command->info('=== Создание расширенных логов ===');

        $zones = Zone::all();
        $nodes = DeviceNode::all();

        $systemLogsCreated = $this->seedSystemLogs();
        $nodeLogsCreated = $this->seedNodeLogs($nodes);
        $aiLogsCreated = $this->seedAiLogs($zones);
        $schedulerLogsCreated = $this->seedSchedulerLogs();

        $this->command->info("Создано системных логов: " . number_format($systemLogsCreated));
        $this->command->info("Создано логов узлов: " . number_format($nodeLogsCreated));
        $this->command->info("Создано AI логов: " . number_format($aiLogsCreated));
        $this->command->info("Создано логов планировщика: " . number_format($schedulerLogsCreated));
        $this->command->info("Всего системных логов: " . SystemLog::count());
        $this->command->info("Всего логов узлов: " . NodeLog::count());
        $this->command->info("Всего AI логов: " . AiLog::count());
        $this->command->info("Всего логов планировщика: " . SchedulerLog::count());
    }

    private function seedSystemLogs(): int
    {
        $created = 0;
        $levels = ['info', 'warning', 'error', 'debug'];
        $messages = [
            'info' => [
                'Система запущена',
                'База данных синхронизирована',
                'Конфигурация загружена',
                'Сервис перезапущен',
                'Резервное копирование выполнено',
            ],
            'warning' => [
                'Высокая нагрузка на систему',
                'Медленный ответ базы данных',
                'Предупреждение о памяти',
                'Необычная активность обнаружена',
            ],
            'error' => [
                'Ошибка подключения к базе данных',
                'Сервис недоступен',
                'Критическая ошибка',
                'Ошибка валидации данных',
            ],
            'debug' => [
                'Отладочное сообщение',
                'Трассировка выполнения',
                'Проверка состояния',
            ],
        ];

        // Создаем логи за последние 2 дня
        for ($daysAgo = 2; $daysAgo >= 0; $daysAgo--) {
            $logCount = rand(5, 10);
            
            for ($i = 0; $i < $logCount; $i++) {
                $level = $levels[rand(0, count($levels) - 1)];
                $message = $messages[$level][rand(0, count($messages[$level]) - 1)];

                SystemLog::create([
                    'level' => $level,
                    'message' => $message . ' (' . ($i + 1) . ')',
                    'context' => [
                        'source' => 'system',
                        'component' => ['api', 'scheduler', 'automation', 'mqtt'][rand(0, 3)],
                        'timestamp' => now()->subDays($daysAgo)->toIso8601String(),
                    ],
                    'created_at' => now()->subDays($daysAgo)->subHours(rand(0, 23))->subMinutes(rand(0, 59)),
                ]);

                $created++;
            }
        }

        return $created;
    }

    private function seedNodeLogs($nodes): int
    {
        $created = 0;
        $levels = ['info', 'warning', 'error'];
        $messages = [
            'info' => [
                'Узел подключен',
                'Телеметрия отправлена',
                'Команда получена',
                'Калибровка завершена',
            ],
            'warning' => [
                'Низкий уровень сигнала',
                'Высокая температура узла',
                'Предупреждение о памяти',
            ],
            'error' => [
                'Ошибка чтения датчика',
                'Ошибка отправки данных',
                'Критическая ошибка узла',
            ],
        ];

        foreach ($nodes as $node) {
            $logCount = match ($node->status) {
                'online' => rand(3, 8),
                'offline' => rand(1, 2),
                default => rand(2, 4),
            };

            for ($i = 0; $i < $logCount; $i++) {
                $level = $levels[rand(0, count($levels) - 1)];
                $message = $messages[$level][rand(0, count($messages[$level]) - 1)];

                NodeLog::create([
                    'node_id' => $node->id,
                    'level' => $level,
                    'message' => $message . ' для узла ' . $node->uid,
                    'context' => [
                        'node_uid' => $node->uid,
                        'node_type' => $node->type,
                        'fw_version' => $node->fw_version,
                    ],
                    'created_at' => now()->subHours(rand(0, 72)),
                ]);

                $created++;
            }
        }

        return $created;
    }

    private function seedAiLogs($zones): int
    {
        $created = 0;
        $actions = ['predict', 'recommend', 'explain', 'diagnostics', 'optimize'];
        
        $actionMessages = [
            'predict' => 'Прогноз параметров выполнен',
            'recommend' => 'Рекомендация сгенерирована',
            'explain' => 'Объяснение предоставлено',
            'diagnostics' => 'Диагностика выполнена',
            'optimize' => 'Оптимизация параметров выполнена',
        ];

        foreach ($zones as $zone) {
            $logCount = match ($zone->status) {
                'RUNNING' => rand(2, 4),
                'PAUSED' => rand(1, 2),
                'STOPPED' => rand(0, 1),
                default => rand(1, 2),
            };

            for ($i = 0; $i < $logCount; $i++) {
                $action = $actions[rand(0, count($actions) - 1)];

                AiLog::create([
                    'zone_id' => $zone->id,
                    'action' => $action,
                    'details' => [
                        'message' => $actionMessages[$action] . ' для зоны ' . $zone->name,
                        'data' => [
                            'metric' => ['ph', 'ec', 'temperature', 'humidity'][rand(0, 3)],
                            'value' => rand(0, 100) / 10,
                            'confidence' => rand(70, 95) / 100,
                        ],
                    ],
                    'created_at' => now()->subHours(rand(0, 168)),
                ]);

                $created++;
            }
        }

        return $created;
    }

    private function seedSchedulerLogs(): int
    {
        $created = 0;
        $taskNames = [
            'recipe_phase',
            'irrigation',
            'dosing',
            'light_control',
            'climate_control',
            'data_backup',
            'maintenance',
        ];
        
        $statuses = ['success', 'failed', 'skipped'];
        $statusWeights = [80, 15, 5];

        // Создаем логи за последние 2 дня
        for ($daysAgo = 2; $daysAgo >= 0; $daysAgo--) {
            $logCount = rand(10, 20);
            
            for ($i = 0; $i < $logCount; $i++) {
                $taskName = $taskNames[rand(0, count($taskNames) - 1)];
                
                // Выбираем статус по весам
                $rand = rand(1, 100);
                $cumulative = 0;
                $status = 'success';
                foreach ($statuses as $index => $stat) {
                    $cumulative += $statusWeights[$index];
                    if ($rand <= $cumulative) {
                        $status = $stat;
                        break;
                    }
                }

                SchedulerLog::create([
                    'task_name' => $taskName,
                    'status' => $status,
                    'details' => [
                        'message' => "Задача {$taskName} выполнена со статусом {$status}",
                        'execution_time_ms' => rand(10, 5000),
                        'zone_id' => rand(1, 20),
                    ],
                    'created_at' => now()->subDays($daysAgo)->subHours(rand(0, 23))->subMinutes(rand(0, 59)),
                ]);

                $created++;
            }
        }

        return $created;
    }
}
