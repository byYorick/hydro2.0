<?php

namespace Database\Seeders;

use App\Models\User;
use Illuminate\Database\Seeder;
use Illuminate\Support\Facades\Hash;

class StartUsersSeeder extends Seeder
{
    public function run(): void
    {
        foreach ($this->baseUsers() as $user) {
            User::query()->updateOrCreate(
                ['email' => $user['email']],
                [
                    'name' => $user['name'],
                    'password' => Hash::make('password'),
                    'role' => $user['role'],
                ]
            );
        }
    }

    /**
     * @return array<int, array{name: string, email: string, role: string}>
     */
    private function baseUsers(): array
    {
        return [
            [
                'name' => 'Admin',
                'email' => 'admin@example.com',
                'role' => 'admin',
            ],
            [
                'name' => 'Agronomist',
                'email' => 'agronomist@example.com',
                'role' => 'agronomist',
            ],
            [
                'name' => 'Operator',
                'email' => 'operator@example.com',
                'role' => 'operator',
            ],
            [
                'name' => 'Viewer',
                'email' => 'viewer@example.com',
                'role' => 'viewer',
            ],
            [
                'name' => 'Engineer',
                'email' => 'engineer@example.com',
                'role' => 'engineer',
            ],
        ];
    }
}
