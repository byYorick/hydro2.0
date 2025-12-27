<?php

namespace Database\Seeders;

use App\Database\Seeders\BaseSeeder;
use App\Models\User;
use Illuminate\Support\Facades\Hash;

/**
 * Расширенный сидер для пользователей
 * Создает разнообразных пользователей с разными ролями и правами
 */
class ExtendedUsersSeeder extends BaseSeeder
{
    /**
     * Зависимости сидера
     */
    public function getDependencies(): array
    {
        return []; // Пользователи не зависят от других данных
    }

    /**
     * Имя сидера
     */
    public function getSeederName(): string
    {
        return 'Extended Users Seeder';
    }

    /**
     * Основная логика сидера
     */
    protected function execute(): void
    {
        $users = $this->getUserData();
        $validatedUsers = $this->createValidatedCollection($users, $this->getValidationRules());

        $this->createWithProgress($validatedUsers, function ($userData) {
            return $this->firstOrCreate(User::class, ['email' => $userData['email']], [
                'name' => $userData['name'],
                'password' => Hash::make($userData['password']),
                'role' => $userData['role'],
                'email_verified_at' => now(),
            ]);
        });
    }

    /**
     * Очистка данных сидера
     */
    public function cleanup(): void
    {
        // Не удаляем AdminUser, так как он нужен всегда
        User::where('email', 'not like', '%admin@hydro.local%')
            ->where('email', 'not like', '%@hydro.local%')
            ->delete();

        $this->command->info('🧹 Очищены тестовые пользователи');
    }

    /**
     * Получить данные пользователей
     */
    private function getUserData(): array
    {
        return [
            // Администраторы
            [
                'name' => 'Главный Администратор',
                'email' => $this->generateEmail('admin', 'chief'),
                'password' => 'password',
                'role' => 'admin',
            ],
            [
                'name' => 'Системный Администратор',
                'email' => $this->generateEmail('admin', 'system'),
                'password' => 'password',
                'role' => 'admin',
            ],
            [
                'name' => 'Администратор Теплиц',
                'email' => $this->generateEmail('admin', 'greenhouse'),
                'password' => 'password',
                'role' => 'admin',
            ],

            // Операторы
            [
                'name' => 'Оператор Смены 1',
                'email' => $this->generateEmail('operator1'),
                'password' => 'password',
                'role' => 'operator',
            ],
            [
                'name' => 'Оператор Смены 2',
                'email' => $this->generateEmail('operator2'),
                'password' => 'password',
                'role' => 'operator',
            ],
            [
                'name' => 'Оператор Смены 3',
                'email' => $this->generateEmail('operator3'),
                'password' => 'password',
                'role' => 'operator',
            ],
            [
                'name' => 'Старший Оператор',
                'email' => $this->generateEmail('senior_operator'),
                'password' => 'password',
                'role' => 'operator',
            ],
            [
                'name' => 'Оператор Зоны A',
                'email' => $this->generateEmail('zone_a_operator'),
                'password' => 'password',
                'role' => 'operator',
            ],
            [
                'name' => 'Оператор Зоны B',
                'email' => $this->generateEmail('zone_b_operator'),
                'password' => 'password',
                'role' => 'operator',
            ],

            // Наблюдатели
            [
                'name' => 'Наблюдатель 1',
                'email' => $this->generateEmail('viewer1'),
                'password' => 'password',
                'role' => 'viewer',
            ],
            [
                'name' => 'Наблюдатель 2',
                'email' => $this->generateEmail('viewer2'),
                'password' => 'password',
                'role' => 'viewer',
            ],
            [
                'name' => 'Аналитик',
                'email' => $this->generateEmail('analyst'),
                'password' => 'password',
                'role' => 'viewer',
            ],
            [
                'name' => 'Менеджер Проекта',
                'email' => $this->generateEmail('manager'),
                'password' => 'password',
                'role' => 'viewer',
            ],

            // Тестовые пользователи
            [
                'name' => 'Тестовый Пользователь',
                'email' => $this->generateEmail('test'),
                'password' => 'password',
                'role' => 'operator',
            ],
            [
                'name' => 'Демо Пользователь',
                'email' => $this->generateEmail('demo'),
                'password' => 'password',
                'role' => 'viewer',
            ],
        ];
    }

    /**
     * Правила валидации данных пользователей
     */
    private function getValidationRules(): array
    {
        return [
            'name' => 'required',
            'email' => 'required',
            'password' => 'required',
            'role' => ['admin', 'operator', 'viewer'],
        ];
    }
}

