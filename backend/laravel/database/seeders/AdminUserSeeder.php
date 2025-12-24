<?php

namespace Database\Seeders;

use App\Models\User;
use Illuminate\Database\Seeder;
use Illuminate\Support\Facades\Hash;

class AdminUserSeeder extends Seeder
{
    public function run(): void
    {
        // Admin user
        User::query()->firstOrCreate(
            ['email' => 'admin@example.com'],
            [
                'name' => 'Admin',
                'password' => Hash::make('password'),
                'role' => 'admin',
            ]
        );

        // Agronomist user (основной профиль для агронома)
        User::query()->firstOrCreate(
            ['email' => 'agronomist@example.com'],
            [
                'name' => 'Agronomist',
                'password' => Hash::make('password'),
                'role' => 'agronomist',
            ]
        );

        // Operator user
        User::query()->firstOrCreate(
            ['email' => 'operator@example.com'],
            [
                'name' => 'Operator',
                'password' => Hash::make('password'),
                'role' => 'operator',
            ]
        );

        // Viewer user
        User::query()->firstOrCreate(
            ['email' => 'viewer@example.com'],
            [
                'name' => 'Viewer',
                'password' => Hash::make('password'),
                'role' => 'viewer',
            ]
        );
    }
}

