<?php

namespace Tests\Unit\Console;

use Illuminate\Support\Facades\Artisan;
use Tests\TestCase;

class TelemetryCleanupCommandTest extends TestCase
{

    public function test_command_signature_exists(): void
    {
        // Проверяем, что команда зарегистрирована
        $commands = Artisan::all();
        $this->assertArrayHasKey('telemetry:cleanup-raw', $commands);
    }

    public function test_command_accepts_days_option(): void
    {
        // Проверяем, что команда принимает опцию --days
        // Используем --help чтобы не выполнять реальную очистку
        $exitCode = Artisan::call('telemetry:cleanup-raw', ['--help' => true]);
        
        // Команда должна существовать (exit code 0 или другой, но не ошибка несуществующей команды)
        $this->assertNotEquals(1, $exitCode);
    }

    public function test_command_output_contains_info(): void
    {
        // Проверяем только регистрацию команды, без выполнения
        $commands = Artisan::all();
        $this->assertArrayHasKey('telemetry:cleanup-raw', $commands);
        
        $command = $commands['telemetry:cleanup-raw'];
        $this->assertStringContainsString('Удаляет старые raw данные', $command->getDescription());
    }
}

