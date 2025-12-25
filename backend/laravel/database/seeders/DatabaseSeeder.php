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
            
            // Каталог типов оборудования
            $this->call(ExtendedInfrastructureAssetsSeeder::class);
            
            // Теплицы и зоны
            $this->call(ExtendedGreenhousesZonesSeeder::class);
            
            // Узлы и каналы
            $this->call(ExtendedNodesChannelsSeeder::class);
            
            // Инфраструктура зон
            $this->call(ExtendedInfrastructureSeeder::class);
            
            // Рецепты и циклы
            $this->call(ExtendedRecipesCyclesSeeder::class);
            
            // Шаблоны стадий роста и маппинг
            $this->call(ExtendedGrowStagesSeeder::class);
            
            // Циклы зон
            $this->call(ExtendedZoneCyclesSeeder::class);
            
            // PID конфигурации
            $this->call(ExtendedZonePidConfigsSeeder::class);
            
            // Растения (расширение)
            $this->call(ExtendedPlantsSeeder::class);
            
            // Связи растений с зонами и рецептами
            $this->call(ExtendedPlantRelationsSeeder::class);
            
            // Телеметрия
            $this->call(ExtendedTelemetrySeeder::class);
            
            // Агрегированная телеметрия
            $this->call(ExtendedTelemetryAggregatedSeeder::class);
            
            // Состояние агрегатора
            $this->call(ExtendedAggregatorStateSeeder::class);
            
            // Команды
            $this->call(ExtendedCommandsSeeder::class);
            
            // Алерты и события
            $this->call(ExtendedAlertsEventsSeeder::class);
            
            // Ожидающие алерты
            $this->call(ExtendedPendingAlertsSeeder::class);
            
            // Ошибки непривязанных узлов
            $this->call(ExtendedUnassignedNodeErrorsSeeder::class);
            
            // AI и прогнозы
            $this->call(ExtendedAIPredictionsSeeder::class);
            
            // Урожаи и аналитика
            $this->call(ExtendedHarvestsSeeder::class);
            
            // Логи
            $this->call(ExtendedLogsSeeder::class);
            
            // Архивные данные
            $this->call(ExtendedArchivesSeeder::class);

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
