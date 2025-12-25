<?php

namespace Database\Seeders;

use App\Models\User;
use Illuminate\Database\Seeder;
use Illuminate\Support\Facades\Hash;

/**
 * Расширенный сидер для пользователей
 * Создает разнообразных пользователей с разными ролями и правами
 */
class ExtendedUsersSeeder extends Seeder
{
    public function run(): void
    {
        $this->command->info('=== Создание расширенных пользователей ===');

        $users = [
            // Администраторы
            [
                'name' => 'Главный Администратор',
                'email' => 'admin@hydro.local',
                'password' => 'password',
                'role' => 'admin',
            ],
            [
                'name' => 'Системный Администратор',
                'email' => 'sysadmin@hydro.local',
                'password' => 'password',
                'role' => 'admin',
            ],
            [
                'name' => 'Администратор Теплиц',
                'email' => 'greenhouse.admin@hydro.local',
                'password' => 'password',
                'role' => 'admin',
            ],

            // Операторы
            [
                'name' => 'Оператор Смены 1',
                'email' => 'operator1@hydro.local',
                'password' => 'password',
                'role' => 'operator',
            ],
            [
                'name' => 'Оператор Смены 2',
                'email' => 'operator2@hydro.local',
                'password' => 'password',
                'role' => 'operator',
            ],
            [
                'name' => 'Оператор Смены 3',
                'email' => 'operator3@hydro.local',
                'password' => 'password',
                'role' => 'operator',
            ],
            [
                'name' => 'Старший Оператор',
                'email' => 'senior.operator@hydro.local',
                'password' => 'password',
                'role' => 'operator',
            ],
            [
                'name' => 'Оператор Зоны A',
                'email' => 'zone.a.operator@hydro.local',
                'password' => 'password',
                'role' => 'operator',
            ],
            [
                'name' => 'Оператор Зоны B',
                'email' => 'zone.b.operator@hydro.local',
                'password' => 'password',
                'role' => 'operator',
            ],

            // Наблюдатели
            [
                'name' => 'Наблюдатель 1',
                'email' => 'viewer1@hydro.local',
                'password' => 'password',
                'role' => 'viewer',
            ],
            [
                'name' => 'Наблюдатель 2',
                'email' => 'viewer2@hydro.local',
                'password' => 'password',
                'role' => 'viewer',
            ],
            [
                'name' => 'Аналитик',
                'email' => 'analyst@hydro.local',
                'password' => 'password',
                'role' => 'viewer',
            ],
            [
                'name' => 'Менеджер Проекта',
                'email' => 'manager@hydro.local',
                'password' => 'password',
                'role' => 'viewer',
            ],

            // Тестовые пользователи
            [
                'name' => 'Тестовый Пользователь',
                'email' => 'test@hydro.local',
                'password' => 'password',
                'role' => 'operator',
            ],
            [
                'name' => 'Демо Пользователь',
                'email' => 'demo@hydro.local',
                'password' => 'password',
                'role' => 'viewer',
            ],
        ];

        $created = 0;
        $updated = 0;

        foreach ($users as $userData) {
            $user = User::firstOrNew(['email' => $userData['email']]);
            
            if ($user->exists) {
                $updated++;
            } else {
                $created++;
            }

            $user->name = $userData['name'];
            $user->password = Hash::make($userData['password']);
            $user->role = $userData['role'];
            $user->email_verified_at = now();
            $user->save();
        }

        $this->command->info("Создано пользователей: {$created}");
        $this->command->info("Обновлено пользователей: {$updated}");
        $this->command->info("Всего пользователей: " . User::count());
    }
}

