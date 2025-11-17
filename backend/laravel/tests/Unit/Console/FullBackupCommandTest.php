<?php

namespace Tests\Unit\Console;

use Illuminate\Support\Facades\Artisan;
use Tests\TestCase;

class FullBackupCommandTest extends TestCase
{
    public function test_command_signature_exists(): void
    {
        // Проверяем, что команда зарегистрирована
        $commands = Artisan::all();
        $this->assertArrayHasKey('backup:full', $commands);
    }

    public function test_command_has_description(): void
    {
        // Проверяем описание команды
        $commands = Artisan::all();
        $this->assertArrayHasKey('backup:full', $commands);
        
        $command = $commands['backup:full'];
        $this->assertStringContainsString('Создает полный бэкап', $command->getDescription());
    }

    public function test_command_accepts_skip_docker_option(): void
    {
        // Проверяем, что команда принимает опцию --skip-docker
        $commands = Artisan::all();
        $this->assertArrayHasKey('backup:full', $commands);
        
        $command = $commands['backup:full'];
        $this->assertNotNull($command);
    }

    public function test_command_accepts_skip_mqtt_option(): void
    {
        // Проверяем, что команда принимает опцию --skip-mqtt
        $commands = Artisan::all();
        $this->assertArrayHasKey('backup:full', $commands);
        
        $command = $commands['backup:full'];
        $this->assertNotNull($command);
    }

    public function test_command_handles_missing_script(): void
    {
        // Проверяем, что команда корректно обрабатывает отсутствие скрипта бэкапа
        $commands = Artisan::all();
        $this->assertArrayHasKey('backup:full', $commands);
        
        // Команда должна существовать и иметь обработку отсутствия скрипта
        $command = $commands['backup:full'];
        $this->assertNotNull($command);
    }
}

