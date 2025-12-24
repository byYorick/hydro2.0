<?php

namespace App\Console\Commands;

use App\Models\User;
use Illuminate\Console\Command;
use Illuminate\Support\Facades\Hash;

class E2EAuthBootstrap extends Command
{
    protected $signature = 'e2e:auth-bootstrap {--email=e2e@test.local} {--role=admin}';
    
    protected $description = 'Создает пользователя и токен для E2E тестов';

    public function handle(): int
    {
        $email = $this->option('email');
        $role = $this->option('role');

        // Создаем или получаем пользователя
        $user = User::firstOrCreate(
            ['email' => $email],
            [
                'name' => 'E2E Test User',
                'password' => Hash::make('e2e-test-password'),
                'role' => $role,
                'email_verified_at' => now(),
            ]
        );

        // Обновляем роль, если пользователь уже существовал
        if ($user->role !== $role) {
            $user->role = $role;
            $user->save();
            $this->info("Обновлена роль пользователя: {$role}");
        }

        // Удаляем старые токены для этого пользователя (опционально, для чистоты)
        // $user->tokens()->delete();

        // Создаем новый токен
        $token = $user->createToken('e2e-test-token')->plainTextToken;

        // Выводим токен в stdout (без дополнительных сообщений для удобства парсинга)
        // В non-verbose режиме выводим только токен
        if ($this->getOutput()->isVerbose()) {
            $this->info("E2E User: {$email} | Role: {$role}");
            $this->info("Token:");
            $this->line($token);
        } else {
            // В non-verbose режиме выводим только токен
            $this->line($token);
        }

        return 0;
    }
}

