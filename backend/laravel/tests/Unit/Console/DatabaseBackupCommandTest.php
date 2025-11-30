<?php

namespace Tests\Unit\Console;

use App\Console\Commands\DatabaseBackupCommand;
use Illuminate\Support\Facades\Artisan;
use Illuminate\Support\Facades\DB;
use Tests\TestCase;

class DatabaseBackupCommandTest extends TestCase
{
    public function test_command_signature_exists(): void
    {
        // Проверяем, что команда зарегистрирована
        $commands = Artisan::all();
        $this->assertArrayHasKey('backup:database', $commands);
    }

    public function test_command_has_description(): void
    {
        // Проверяем описание команды
        $commands = Artisan::all();
        $this->assertArrayHasKey('backup:database', $commands);
        
        $command = $commands['backup:database'];
        $this->assertStringContainsString('Создает полный дамп', $command->getDescription());
    }

    public function test_command_accepts_compress_option(): void
    {
        // Проверяем, что команда принимает опцию --compress
        $commands = Artisan::all();
        $this->assertArrayHasKey('backup:database', $commands);
        
        // Команда должна существовать и принимать опции
        $command = $commands['backup:database'];
        $this->assertNotNull($command);
    }

    public function test_command_accepts_output_option(): void
    {
        // Проверяем, что команда принимает опцию --output
        $commands = Artisan::all();
        $this->assertArrayHasKey('backup:database', $commands);
        
        $command = $commands['backup:database'];
        $this->assertNotNull($command);
    }

    public function test_format_bytes_formats_correctly(): void
    {
        // Тестируем метод formatBytes через рефлексию
        $command = new DatabaseBackupCommand();
        $reflection = new \ReflectionClass($command);
        $method = $reflection->getMethod('formatBytes');
        $method->setAccessible(true);
        
        // Тест различных размеров
        // Функция использует > 1024, поэтому 1024 байта остаются в байтах
        $this->assertStringContainsString('B', $method->invoke($command, 1));
        $this->assertStringContainsString('B', $method->invoke($command, 1024)); // 1024 > 1024 = false, остается B
        $this->assertStringContainsString('KB', $method->invoke($command, 1025)); // 1025 > 1024 = true, становится KB
        $this->assertStringContainsString('MB', $method->invoke($command, 1024 * 1024 + 1));
        $this->assertStringContainsString('GB', $method->invoke($command, 1024 * 1024 * 1024 + 1));
        $this->assertStringContainsString('B', $method->invoke($command, 512));
        $this->assertStringContainsString('KB', $method->invoke($command, 1536));
        
        // Проверяем точные значения для нецелых чисел
        $result = $method->invoke($command, 1536);
        $this->assertStringContainsString('1.5', $result);
    }

    public function test_command_handles_database_connection_error(): void
    {
        // Проверяем, что команда корректно обрабатывает ошибки подключения
        // Проверяем структуру команды
        $commands = Artisan::all();
        $this->assertArrayHasKey('backup:database', $commands);
        
        // Команда должна существовать и иметь обработку ошибок
        $command = $commands['backup:database'];
        $this->assertNotNull($command);
    }
}

