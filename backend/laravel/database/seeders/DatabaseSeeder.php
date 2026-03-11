<?php

namespace Database\Seeders;

use Illuminate\Database\Seeder;
use Illuminate\Support\Facades\Log;

/**
 * Главный сидер приложения
 * Управляет выполнением всех сидеров с правильными зависимостями
 */
class DatabaseSeeder extends Seeder
{
    /**
     * Группы сидеров по приоритетам выполнения
     */
    private array $seederGroups = [
        'critical' => [
            'description' => 'Критически важные данные (всегда выполняются)',
            'seeders' => [
                AdminUserSeeder::class,
                PresetSeeder::class,
                PlantTaxonomySeeder::class,
            ],
        ],
        'infrastructure' => [
            'description' => 'Инфраструктура системы',
            'seeders' => [
                ExtendedUsersSeeder::class,
                ExtendedGreenhousesZonesSeeder::class,
                ExtendedInfrastructureAssetsSeeder::class,
                ExtendedNodesChannelsSeeder::class,
                ExtendedInfrastructureSeeder::class,
            ],
        ],
        'business_logic' => [
            'description' => 'Бизнес-логика и рецепты',
            'seeders' => [
                ExtendedRecipesCyclesSeeder::class,
                ExtendedGrowStagesSeeder::class,
                ExtendedZonePidConfigsSeeder::class,
                ExtendedPlantsSeeder::class,
                ExtendedAutomationProfilesSeeder::class,
            ],
        ],
        'operational_data' => [
            'description' => 'Операционные данные (телеметрия, команды, алерты)',
            'seeders' => [
                ExtendedTelemetrySeeder::class,
                ExtendedTelemetryAggregatedSeeder::class,
                ExtendedAggregatorStateSeeder::class,
                ExtendedCommandsSeeder::class,
                ExtendedAlertsEventsSeeder::class,
                ExtendedPendingAlertsSeeder::class,
                ExtendedUnassignedNodeErrorsSeeder::class,
            ],
        ],
        'analytics' => [
            'description' => 'Аналитика и AI',
            'seeders' => [
                ExtendedAIPredictionsSeeder::class,
                ExtendedHarvestsSeeder::class,
            ],
        ],
        'logs_and_archives' => [
            'description' => 'Логи и архивные данные',
            'seeders' => [
                ExtendedLogsSeeder::class,
                ExtendedArchivesSeeder::class,
            ],
        ],
    ];

    /**
     * Seed the application's database.
     */
    public function run(): void
    {
        $startTime = microtime(true);
        $this->command->info('🚀 Запуск рефакторинговых сидеров Hydro 2.0');

        // Определяем окружение выполнения
        $environment = app()->environment();
        $isDevelopment = in_array($environment, ['local', 'development']);
        $isTesting = in_array($environment, ['testing', 'e2e']);

        $this->command->info("📍 Окружение: {$environment}");
        $this->command->info('⚙️  Режим разработки: '.($isDevelopment ? 'Да' : 'Нет'));
        $this->command->info('🧪 Режим тестирования: '.($isTesting ? 'Да' : 'Нет'));

        $seedProfile = config('hydro.seed_profile');
        $seedProfile = $seedProfile ? strtolower($seedProfile) : 'full';
        $this->command->info("🧩 Профиль сидеров: {$seedProfile}");

        if ($seedProfile === 'start') {
            $this->command->info('⚡ Запуск стартовых сидеров (только админ и агроном)');
            $this->call(StartUsersSeeder::class);
            $this->command->info('✅ Стартовые сидеры выполнены');

            return;
        }

        if ($seedProfile === 'lite') {
            $this->runLiteSeeders($isTesting);

            return;
        }

        // Выполняем группы сидеров
        $totalSeeders = 0;
        $executedSeeders = 0;

        foreach ($this->seederGroups as $groupName => $groupConfig) {
            $seeders = $this->filterSeedersByEnvironment($groupConfig['seeders'], $groupName, $isDevelopment, $isTesting);

            if (empty($seeders)) {
                continue;
            }

            $this->command->info("📦 Группа: {$groupConfig['description']}");

            $groupResults = $this->executeSeederGroup($seeders, $groupName);
            $totalSeeders += count($seeders);
            $executedSeeders += $groupResults['executed'];

            $this->logGroupResults($groupResults);
        }

        // Специальные сидеры для тестирования
        if ($isTesting) {
            $this->command->info('🧪 Специальные E2E сидеры...');
            $this->executeSpecialSeeders();
        }

        // Финальная статистика
        $duration = round(microtime(true) - $startTime, 2);
        $this->command->info("✅ Все сидеры выполнены за {$duration}s");
        $this->command->info("📊 Выполнено сидеров: {$executedSeeders}/{$totalSeeders}");

        Log::info('Database seeding completed', [
            'duration' => $duration,
            'environment' => $environment,
            'total_seeders' => $totalSeeders,
            'executed_seeders' => $executedSeeders,
        ]);
    }

    /**
     * Фильтрация сидеров по окружению
     */
    private function filterSeedersByEnvironment(array $seeders, string $groupName, bool $isDevelopment, bool $isTesting): array
    {
        if ($groupName === 'critical') {
            return $seeders;
        }

        return array_filter($seeders, function ($seeder) use ($isDevelopment, $isTesting) {
            // E2E сидеры только для тестирования
            if (str_contains($seeder, 'E2ESeeder') || str_contains($seeder, 'E2e')) {
                return $isTesting;
            }

            // Остальные сидеры только для разработки
            return $isDevelopment;
        });
    }

    private function runLiteSeeders(bool $isTesting): void
    {
        $this->command->info('⚡ Запуск облегченного набора сидеров');

        $seeders = [
            SingleZoneServiceSeeder::class,
        ];

        foreach ($seeders as $seederClass) {
            $this->call($seederClass);
        }

        if ($isTesting) {
            $this->executeSpecialSeeders();
        }

        $this->command->info('✅ Облегченный набор сидеров выполнен');
    }

    /**
     * Выполнение группы сидеров
     */
    private function executeSeederGroup(array $seeders, string $groupName): array
    {
        $results = [
            'executed' => 0,
            'failed' => 0,
            'skipped' => 0,
            'errors' => [],
        ];

        foreach ($seeders as $seederClass) {
            try {
                $this->command->info('  ▶️  Выполнение: '.basename($seederClass, 'Seeder'));

                // Проверяем, существует ли класс
                if (! class_exists($seederClass)) {
                    $this->command->warn("  ⚠️  Сидер не найден: {$seederClass}");
                    $results['skipped']++;

                    continue;
                }

                // Выполняем сидер
                $this->call($seederClass);
                $results['executed']++;

            } catch (\Throwable $e) {
                $this->command->error("  ❌ Ошибка в сидере {$seederClass}: {$e->getMessage()}");
                $results['failed']++;
                $results['errors'][] = [
                    'seeder' => $seederClass,
                    'error' => $e->getMessage(),
                ];

                Log::error("Seeder execution failed: {$seederClass}", [
                    'error' => $e->getMessage(),
                    'trace' => $e->getTraceAsString(),
                    'group' => $groupName,
                ]);

                // Продолжаем выполнение других сидеров
            }
        }

        return $results;
    }

    /**
     * Выполнение специальных E2E сидеров
     */
    private function executeSpecialSeeders(): void
    {
        $specialSeeders = [
            AutomationEngineE2ESeeder::class,
        ];

        foreach ($specialSeeders as $seederClass) {
            try {
                if (class_exists($seederClass)) {
                    $this->call($seederClass);
                }
            } catch (\Throwable $e) {
                $this->command->error("Ошибка в специальном сидере {$seederClass}: {$e->getMessage()}");
                Log::error("Special seeder failed: {$seederClass}", [
                    'error' => $e->getMessage(),
                ]);
            }
        }
    }

    /**
     * Логирование результатов группы
     */
    private function logGroupResults(array $results): void
    {
        if ($results['executed'] > 0) {
            $this->command->info("  ✅ Выполнено: {$results['executed']}");
        }

        if ($results['skipped'] > 0) {
            $this->command->warn("  ⏭️  Пропущено: {$results['skipped']}");
        }

        if ($results['failed'] > 0) {
            $this->command->error("  ❌ Ошибок: {$results['failed']}");
        }

        $this->command->newLine();
    }

    /**
     * Метод для повторного запуска отдельных групп сидеров
     */
    public function runGroup(string $groupName): void
    {
        if (! isset($this->seederGroups[$groupName])) {
            $this->command->error("Группа '{$groupName}' не найдена");
            $this->command->info('Доступные группы:');
            foreach ($this->seederGroups as $name => $config) {
                $this->command->info("  - {$name}: {$config['description']}");
            }

            return;
        }

        $groupConfig = $this->seederGroups[$groupName];
        $seeders = $groupConfig['seeders'];

        $this->command->info("🔄 Повторный запуск группы: {$groupConfig['description']}");
        $results = $this->executeSeederGroup($seeders, $groupName);
        $this->logGroupResults($results);
    }

    /**
     * Метод для запуска отдельных сидеров с зависимостями
     */
    public function runSeeder(string $seederClass): void
    {
        $factory = app(\App\Database\Seeders\SeederFactory::class);

        try {
            $seeder = $factory->make($seederClass);
            $dependencies = $seeder->getDependencies();

            if (! empty($dependencies)) {
                $this->command->info("🔗 Проверка зависимостей для {$seederClass}...");
                $depResults = $factory->validateAllDependencies([$seederClass]);

                if (! empty($depResults['invalid'])) {
                    $this->command->error('❌ Зависимости не выполнены:');
                    foreach ($depResults['invalid'] as $invalid) {
                        $this->command->error("  - {$invalid['seeder']}: отсутствуют ".implode(', ', $invalid['missing_dependencies']));
                    }

                    return;
                }
                $this->command->info('✅ Все зависимости выполнены');
            }

            $this->command->info("🚀 Запуск сидера: {$seederClass}");
            $this->call($seederClass);

        } catch (\Throwable $e) {
            $this->command->error("❌ Ошибка при запуске сидера {$seederClass}: {$e->getMessage()}");
        }
    }

    /**
     * Метод для очистки данных по группам
     */
    public function cleanupGroup(string $groupName): void
    {
        if (! isset($this->seederGroups[$groupName])) {
            $this->command->error("Группа '{$groupName}' не найдена");

            return;
        }

        $groupConfig = $this->seederGroups[$groupName];
        $seeders = $groupConfig['seeders'];

        $this->command->info("🧹 Очистка группы: {$groupConfig['description']}");

        $factory = app(\App\Database\Seeders\SeederFactory::class);
        $cleaned = 0;

        foreach ($seeders as $seederClass) {
            try {
                $seeder = $factory->make($seederClass);
                $seeder->cleanup();
                $this->command->info('  ✅ Очищено: '.basename($seederClass, 'Seeder'));
                $cleaned++;
            } catch (\Throwable $e) {
                $this->command->warn("  ⚠️  Ошибка очистки {$seederClass}: {$e->getMessage()}");
            }
        }

        $this->command->info("🧹 Очищено сидеров: {$cleaned}");
    }

    /**
     * Метод для получения информации о сидерах
     */
    public function info(): void
    {
        $this->command->info('📊 Информация о сидерах Hydro 2.0');
        $this->command->line('');

        $factory = app(\App\Database\Seeders\SeederFactory::class);
        $totalSeeders = 0;

        foreach ($this->seederGroups as $groupName => $groupConfig) {
            $this->command->info("📦 Группа: {$groupConfig['description']} ({$groupName})");

            foreach ($groupConfig['seeders'] as $seederClass) {
                $totalSeeders++;
                $info = $factory->getSeederInfo($seederClass);

                $status = isset($info['error']) ? '❌' : '✅';
                $this->command->info("  {$status} ".basename($seederClass, 'Seeder'));

                if (isset($info['error'])) {
                    $this->command->error("    Ошибка: {$info['error']}");
                } elseif (! empty($info['dependencies'])) {
                    $this->command->info('    Зависимости: '.implode(', ', $info['dependencies']));
                } else {
                    $this->command->info('    Зависимости: нет');
                }
            }

            $this->command->line('');
        }

        $this->command->info("📈 Всего сидеров: {$totalSeeders}");
    }

    /**
     * Метод для очистки данных (реверс сидирования)
     */
    public function cleanup(): void
    {
        $this->command->warn('🧹 Очистка данных сидеров не реализована');
        $this->command->warn('Для полной очистки используйте: php artisan migrate:fresh');
    }
}
