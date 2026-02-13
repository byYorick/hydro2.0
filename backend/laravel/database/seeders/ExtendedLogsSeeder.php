<?php

namespace Database\Seeders;

use App\Models\AiLog;
use App\Models\DeviceNode;
use App\Models\NodeLog;
use App\Models\SchedulerLog;
use App\Models\SystemLog;
use App\Models\Zone;
use Illuminate\Database\Seeder;
use Illuminate\Support\Str;

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
        $schedulerLogsCreated = $this->seedSchedulerLogs($zones);

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

    private function seedSchedulerLogs($zones): int
    {
        $created = 0;
        $taskTypes = [
            'irrigation',
            'lighting',
            'ventilation',
            'solution_change',
            'mist',
            'diagnostics',
        ];
        $statusWeights = [
            'accepted' => 14,
            'running' => 18,
            'completed' => 36,
            'failed' => 12,
            'rejected' => 7,
            'expired' => 5,
            'timeout' => 5,
            'not_found' => 3,
        ];

        $zoneIds = $zones->pluck('id')->all();
        if (empty($zoneIds)) {
            return 0;
        }

        // Создаем логи за последние 2 дня
        for ($daysAgo = 2; $daysAgo >= 0; $daysAgo--) {
            $logCount = rand(10, 20);
            
            for ($i = 0; $i < $logCount; $i++) {
                $createdAt = now()->subDays($daysAgo)->subHours(rand(0, 23))->subMinutes(rand(0, 59));
                $status = $this->pickWeightedStatus($statusWeights);
                $taskType = $taskTypes[rand(0, count($taskTypes) - 1)];
                $zoneId = (int) $zoneIds[array_rand($zoneIds)];
                $taskId = 'st-'.$zoneId.'-'.Str::lower(Str::random(10));
                $correlationId = "sch:z{$zoneId}:{$taskType}:".Str::lower(Str::random(12));
                $scheduledFor = $createdAt->copy()->subMinutes(rand(1, 30));
                $dueAt = $scheduledFor->copy()->addSeconds(rand(20, 90));
                $expiresAt = $dueAt->copy()->addMinutes(rand(2, 10));

                $details = [
                    'task_id' => $taskId,
                    'zone_id' => $zoneId,
                    'task_type' => $taskType,
                    'status' => $status,
                    'correlation_id' => $correlationId,
                    'scheduled_for' => $scheduledFor->toIso8601String(),
                    'due_at' => $dueAt->toIso8601String(),
                    'expires_at' => $expiresAt->toIso8601String(),
                    'contract_version' => 'scheduler_task_v2',
                    'message' => "Scheduler task {$taskType} processed with status {$status}",
                    'execution_time_ms' => rand(20, 5000),
                ];

                if (! in_array($status, ['accepted', 'running'], true)) {
                    $details['result'] = $this->buildSchedulerResult($status);
                }

                SchedulerLog::create([
                    'task_name' => $taskType,
                    'status' => $status,
                    'details' => $details,
                    'created_at' => $createdAt,
                ]);

                $created++;
            }
        }

        return $created;
    }

    private function pickWeightedStatus(array $weights): string
    {
        $random = rand(1, array_sum($weights));
        $acc = 0;
        foreach ($weights as $status => $weight) {
            $acc += $weight;
            if ($random <= $acc) {
                return $status;
            }
        }

        return 'failed';
    }

    private function buildSchedulerResult(string $status): array
    {
        return match ($status) {
            'completed' => [
                'action_required' => true,
                'decision' => 'run',
                'reason_code' => 'required_nodes_checked',
                'error_code' => null,
                'command_submitted' => true,
                'command_effect_confirmed' => true,
                'commands_total' => 1,
                'commands_effect_confirmed' => 1,
                'commands_failed' => 0,
            ],
            'failed' => [
                'action_required' => true,
                'decision' => 'fail',
                'reason_code' => 'command_effect_not_confirmed',
                'error_code' => 'command_effect_not_confirmed',
                'command_submitted' => true,
                'command_effect_confirmed' => false,
                'commands_total' => 1,
                'commands_effect_confirmed' => 0,
                'commands_failed' => 1,
            ],
            'rejected' => [
                'action_required' => false,
                'decision' => 'skip',
                'reason_code' => 'task_due_deadline_exceeded',
                'error_code' => 'task_due_deadline_exceeded',
                'command_submitted' => false,
                'command_effect_confirmed' => false,
                'commands_total' => 0,
                'commands_effect_confirmed' => 0,
                'commands_failed' => 0,
            ],
            'expired' => [
                'action_required' => false,
                'decision' => 'skip',
                'reason_code' => 'task_expired',
                'error_code' => 'task_expired',
                'command_submitted' => false,
                'command_effect_confirmed' => false,
                'commands_total' => 0,
                'commands_effect_confirmed' => 0,
                'commands_failed' => 0,
            ],
            'timeout' => [
                'action_required' => false,
                'decision' => 'skip',
                'reason_code' => 'task_status_timeout',
                'error_code' => 'task_status_timeout',
                'command_submitted' => false,
                'command_effect_confirmed' => false,
                'commands_total' => 0,
                'commands_effect_confirmed' => 0,
                'commands_failed' => 0,
            ],
            'not_found' => [
                'action_required' => false,
                'decision' => 'skip',
                'reason_code' => 'task_status_not_found',
                'error_code' => 'task_status_not_found',
                'command_submitted' => false,
                'command_effect_confirmed' => false,
                'commands_total' => 0,
                'commands_effect_confirmed' => 0,
                'commands_failed' => 0,
            ],
            default => [
                'action_required' => false,
                'decision' => 'skip',
                'reason_code' => 'task_execution_failed',
                'error_code' => 'task_execution_failed',
                'command_submitted' => false,
                'command_effect_confirmed' => false,
                'commands_total' => 0,
                'commands_effect_confirmed' => 0,
                'commands_failed' => 0,
            ],
        };
    }
}
