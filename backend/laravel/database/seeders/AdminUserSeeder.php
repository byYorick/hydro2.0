<?php

namespace Database\Seeders;

use App\Models\User;
use Illuminate\Database\Seeder;
use Illuminate\Support\Facades\Hash;

class AdminUserSeeder extends Seeder
{
    public function run(): void
    {
        // Детерминированные dev-учетки: повторный сидинг исправляет уже существующие записи.
        User::query()->updateOrCreate(
            ['email' => 'admin@example.com'],
            [
                'name' => 'Admin',
                'password' => Hash::make('password'),
                'role' => 'admin',
            ]
        );

        // Agronomist user (основной профиль для агронома)
        User::query()->updateOrCreate(
            ['email' => 'agronomist@example.com'],
            [
                'name' => 'Agronomist',
                'password' => Hash::make('password'),
                'role' => 'agronomist',
            ]
        );

        // Operator user
        User::query()->updateOrCreate(
            ['email' => 'operator@example.com'],
            [
                'name' => 'Operator',
                'password' => Hash::make('password'),
                'role' => 'operator',
            ]
        );

        // Viewer user
        User::query()->updateOrCreate(
            ['email' => 'viewer@example.com'],
            [
                'name' => 'Viewer',
                'password' => Hash::make('password'),
                'role' => 'viewer',
            ]
        );
    }
}
