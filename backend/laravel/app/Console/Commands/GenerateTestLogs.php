<?php

namespace App\Console\Commands;

use App\Models\SystemLog;
use Illuminate\Console\Command;

class GenerateTestLogs extends Command
{
    protected $signature = 'logs:generate-test {count=50 : Number of logs to generate}';
    protected $description = 'Generate test system logs for audit page';

    public function handle()
    {
        $count = (int) $this->argument('count');
        
        $levels = ['debug', 'info', 'warning', 'error'];
        $messages = [
            'info' => [
                'Система запущена успешно',
                'Пользователь вошел в систему',
                'Конфигурация загружена',
                'База данных подключена',
                'Кеш очищен',
                'Задача выполнена успешно',
            ],
            'warning' => [
                'Высокое использование памяти',
                'Медленный ответ API',
                'Попытка неавторизованного доступа',
                'Превышен лимит запросов',
                'Временная недоступность сервиса',
            ],
            'error' => [
                'Ошибка подключения к базе данных',
                'Не удалось отправить email',
                'Ошибка валидации данных',
                'Сервис недоступен',
                'Ошибка при сохранении данных',
            ],
            'debug' => [
                'Отладочная информация',
                'Проверка конфигурации',
                'Тестовое сообщение',
            ],
        ];

        $this->info("Генерация {$count} тестовых логов...");

        for ($i = 0; $i < $count; $i++) {
            $level = $levels[array_rand($levels)];
            $messageList = $messages[$level] ?? $messages['info'];
            $message = $messageList[array_rand($messageList)] . ' #' . ($i + 1);
            
            $context = [
                'source' => 'test',
                'iteration' => $i + 1,
                'timestamp' => now()->toIso8601String(),
            ];

            if ($level === 'error') {
                $context['error_code'] = 'TEST_' . rand(1000, 9999);
                $context['stack_trace'] = 'Test stack trace for error #' . ($i + 1);
            }

            SystemLog::create([
                'level' => $level,
                'message' => $message,
                'context' => $context,
                'created_at' => now()->subHours(rand(0, 168)), // Последние 7 дней
            ]);
        }

        $this->info("✓ Создано {$count} тестовых логов");
        $this->info("Проверьте страницу /audit для просмотра логов");

        return Command::SUCCESS;
    }
}

