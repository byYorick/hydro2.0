<?php

namespace Database\Seeders;

use App\Models\User;
use Illuminate\Database\Seeder;
use Illuminate\Support\Facades\Hash;

class StartUsersSeeder extends Seeder
{
    public function run(): void
    {
        User::query()->firstOrCreate(
            ['email' => 'admin@example.com'],
            [
                'name' => 'Admin',
                'password' => Hash::make('password'),
                'role' => 'admin',
            ]
        );

        User::query()->firstOrCreate(
            ['email' => 'agronomist@example.com'],
            [
                'name' => 'Agronomist',
                'password' => Hash::make('password'),
                'role' => 'agronomist',
            ]
        );
    }
}
