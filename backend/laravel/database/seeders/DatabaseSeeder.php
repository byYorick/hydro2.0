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
        $this->command->info('=== Запуск расширенных сидеров ===');

        // Базовые сидеры (всегда выполняются)
        $this->command->info('1. Базовые данные...');
        $this->call(AdminUserSeeder::class);
        $this->call(PresetSeeder::class);
        $this->call(PlantTaxonomySeeder::class);

        // Расширенные сидеры (в development/local окружении)
        if (app()->environment('local', 'development')) {
            $this->command->info('2. Расширенные данные...');
            
            // Пользователи
            $this->call(ExtendedUsersSeeder::class);
            
            // Теплицы и зоны
            $this->call(ExtendedGreenhousesZonesSeeder::class);
            
            // Узлы и каналы
            $this->call(ExtendedNodesChannelsSeeder::class);
            
            // Инфраструктура
            $this->call(ExtendedInfrastructureSeeder::class);
            
            // Рецепты и циклы
            $this->call(ExtendedRecipesCyclesSeeder::class);
            
            // Растения (расширение)
            $this->call(ExtendedPlantsSeeder::class);
            
            // Телеметрия
            $this->call(ExtendedTelemetrySeeder::class);
            
            // Команды
            $this->call(ExtendedCommandsSeeder::class);
            
            // Алерты и события
            $this->call(ExtendedAlertsEventsSeeder::class);
            
            // AI и прогнозы
            $this->call(ExtendedAIPredictionsSeeder::class);
            
            // Урожаи и аналитика
            $this->call(ExtendedHarvestsSeeder::class);
            
            // Логи
            $this->call(ExtendedLogsSeeder::class);

            // Старые сидеры для совместимости (опционально)
            // $this->call(FullServiceTestSeeder::class);
            // $this->call(ProgressTestSeeder::class);
        }

        // Seed E2E automation engine data (only in testing/e2e environment)
        if (app()->environment('testing', 'e2e')) {
            $this->command->info('3. E2E данные...');
            $this->call(AutomationEngineE2ESeeder::class);
        }

        $this->command->info('=== Сидеры завершены ===');
    }
}
