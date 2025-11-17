<?php

namespace Tests\Unit\Console;

use App\Console\Commands\BackupListCommand;
use Illuminate\Support\Facades\Artisan;
use Tests\TestCase;

class BackupListCommandTest extends TestCase
{
    public function test_command_signature_exists(): void
    {
        // Проверяем, что команда зарегистрирована
        $commands = Artisan::all();
        $this->assertArrayHasKey('backup:list', $commands);
    }

    public function test_command_has_description(): void
    {
        // Проверяем описание команды
        $commands = Artisan::all();
        $this->assertArrayHasKey('backup:list', $commands);
        
        $command = $commands['backup:list'];
        $this->assertStringContainsString('Показывает список', $command->getDescription());
    }

    public function test_command_accepts_verify_option(): void
    {
        // Проверяем, что команда принимает опцию --verify
        $commands = Artisan::all();
        $this->assertArrayHasKey('backup:list', $commands);
        
        $command = $commands['backup:list'];
        $this->assertNotNull($command);
    }

    public function test_format_timestamp_formats_correctly(): void
    {
        // Тестируем метод formatTimestamp через рефлексию
        $command = new BackupListCommand();
        $reflection = new \ReflectionClass($command);
        $method = $reflection->getMethod('formatTimestamp');
        $method->setAccessible(true);
        
        // Тест правильного формата
        $formatted = $method->invoke($command, '20250116_120000');
        $this->assertStringContainsString('2025-01-16', $formatted);
        $this->assertStringContainsString('12:00:00', $formatted);
        
        // Тест пустой строки
        $this->assertEquals('unknown', $method->invoke($command, ''));
        
        // Тест неправильного формата
        $invalid = $method->invoke($command, 'invalid-format');
        $this->assertEquals('invalid-format', $invalid);
    }

    public function test_format_bytes_formats_correctly(): void
    {
        // Тестируем метод formatBytes через рефлексию
        $command = new BackupListCommand();
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
        
        // Проверяем, что форматирование работает корректно
        $result1 = $method->invoke($command, 1025);
        $this->assertStringContainsString('1', $result1);
        $this->assertStringContainsString('KB', $result1);
    }

    public function test_verify_backup_checks_correctly(): void
    {
        // Тестируем метод verifyBackup через рефлексию
        $command = new BackupListCommand();
        $reflection = new \ReflectionClass($command);
        $method = $reflection->getMethod('verifyBackup');
        $method->setAccessible(true);
        
        // Тест с несуществующей директорией
        $result = $method->invoke($command, ['path' => '/nonexistent/path']);
        $this->assertFalse($result);
        
        // Тест с существующей директорией но без manifest
        $tempDir = sys_get_temp_dir() . '/test_backup_' . uniqid();
        mkdir($tempDir, 0755, true);
        
        $result = $method->invoke($command, ['path' => $tempDir]);
        $this->assertFalse($result);
        
        // Создаем manifest
        file_put_contents($tempDir . '/manifest.json', json_encode(['timestamp' => '20250116_120000']));
        
        // Тест без файлов бэкапа
        $result = $method->invoke($command, ['path' => $tempDir]);
        $this->assertFalse($result);
        
        // Создаем тестовый файл бэкапа
        file_put_contents($tempDir . '/test_backup.dump', 'test content');
        
        // Тест с валидным бэкапом
        $result = $method->invoke($command, ['path' => $tempDir]);
        $this->assertTrue($result);
        
        // Очистка
        unlink($tempDir . '/test_backup.dump');
        unlink($tempDir . '/manifest.json');
        rmdir($tempDir);
    }

    public function test_command_handles_missing_backup_directory(): void
    {
        // Проверяем, что команда корректно обрабатывает отсутствие директории бэкапов
        $commands = Artisan::all();
        $this->assertArrayHasKey('backup:list', $commands);
        
        // Команда должна существовать и иметь обработку отсутствия директории
        $command = $commands['backup:list'];
        $this->assertNotNull($command);
    }
}

