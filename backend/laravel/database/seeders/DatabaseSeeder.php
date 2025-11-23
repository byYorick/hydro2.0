<?php

namespace Database\Seeders;

use App\Models\User;
use Illuminate\Database\Seeder;

class DatabaseSeeder extends Seeder
{
    /**
     * Seed the application's database.
     */
    public function run(): void
    {
        // Seed admin user
        $this->call(AdminUserSeeder::class);

        // Seed presets (plant growing presets)
        $this->call(PresetSeeder::class);

        // Seed demo data (only in development)
        if (app()->environment('local', 'development')) {
            // Полное заполнение всех таблиц для тестирования всех сервисов
            // PresetSeeder уже выполнен выше
            $this->call(FullServiceTestSeeder::class);
        }
    }
}
