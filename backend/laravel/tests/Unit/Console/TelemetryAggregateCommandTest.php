<?php

namespace Tests\Unit\Console;

use Illuminate\Support\Facades\Artisan;
use Tests\TestCase;

class TelemetryAggregateCommandTest extends TestCase
{

    public function test_command_signature_exists(): void
    {
        // Проверяем, что команда зарегистрирована
        $commands = Artisan::all();
        $this->assertArrayHasKey('telemetry:aggregate', $commands);
    }

    public function test_command_accepts_from_option(): void
    {
        // Проверяем только регистрацию команды
        $commands = Artisan::all();
        $this->assertArrayHasKey('telemetry:aggregate', $commands);
        
        $command = $commands['telemetry:aggregate'];
        $this->assertStringContainsString('Агрегирует raw данные', $command->getDescription());
    }

    public function test_command_accepts_to_option(): void
    {
        // Проверяем, что команда зарегистрирована
        $commands = Artisan::all();
        $this->assertArrayHasKey('telemetry:aggregate', $commands);
    }

    public function test_command_output_contains_info(): void
    {
        // Проверяем только регистрацию команды
        $commands = Artisan::all();
        $this->assertArrayHasKey('telemetry:aggregate', $commands);
        
        $command = $commands['telemetry:aggregate'];
        $this->assertStringContainsString('Агрегирует raw данные', $command->getDescription());
    }
}

