<?php

namespace App\Console\Commands;

use App\Database\Seeders\SeederFactory;
use Database\Seeders\DatabaseSeeder;
use Illuminate\Console\Command;

/**
 * Команда для управления сидерами с расширенной функциональностью
 */
class SeederCommand extends Command
{
    /**
     * The name and signature of the console command.
     *
     * @var string
     */
    protected $signature = 'hydro:seeders
                            {action : Действие (run, group, seeder, cleanup, info)}
                            {target? : Цель действия (группа или класс сидера)}
                            {--force : Принудительное выполнение без подтверждения}';

    /**
     * The console command description.
     *
     * @var string
     */
    protected $description = 'Управление сидерами с расширенной функциональностью';

    /**
     * Execute the console command.
     */
    public function handle()
    {
        $action = $this->argument('action');
        $target = $this->argument('target');
        $force = $this->option('force');

        switch ($action) {
            case 'run':
                $this->runFullSeed();
                break;

            case 'group':
                if (!$target) {
                    $this->error('Не указана группа сидеров. Используйте: php artisan seeders:manage group <group_name>');
                    $this->showAvailableGroups();
                    return;
                }
                $this->runSeederGroup($target, $force);
                break;

            case 'seeder':
                if (!$target) {
                    $this->error('Не указан класс сидера. Используйте: php artisan seeders:manage seeder <SeederClass>');
                    return;
                }
                $this->runIndividualSeeder($target, $force);
                break;

            case 'cleanup':
                if (!$target) {
                    $this->error('Не указана группа для очистки. Используйте: php artisan seeders:manage cleanup <group_name>');
                    $this->showAvailableGroups();
                    return;
                }
                $this->cleanupGroup($target, $force);
                break;

            case 'info':
                $this->showSeederInfo();
                break;

            default:
                $this->error("Неизвестное действие: {$action}");
                $this->showHelp();
                return;
        }
    }

    /**
     * Полный запуск всех сидеров
     */
    private function runFullSeed(): void
    {
        if (!$this->confirm('Запустить все сидеры? Это может занять много времени.', true)) {
            return;
        }

        $this->info('🚀 Запуск полного сидирования...');
        $seeder = app(DatabaseSeeder::class);
        $seeder->run();
    }

    /**
     * Запуск группы сидеров
     */
    private function runSeederGroup(string $groupName, bool $force): void
    {
        if (!$force && !$this->confirm("Запустить группу сидеров '{$groupName}'?", true)) {
            return;
        }

        $this->info("📦 Запуск группы: {$groupName}");
        $seeder = app(DatabaseSeeder::class);
        $seeder->runGroup($groupName);
    }

    /**
     * Запуск индивидуального сидера
     */
    private function runIndividualSeeder(string $seederClass, bool $force): void
    {
        // Добавляем суффикс Seeder если не указан
        if (!str_ends_with($seederClass, 'Seeder')) {
            $seederClass .= 'Seeder';
        }

        // Добавляем namespace если не указан
        if (!str_contains($seederClass, '\\')) {
            $seederClass = "Database\\Seeders\\{$seederClass}";
        }

        if (!$force && !$this->confirm("Запустить сидер '{$seederClass}'?", true)) {
            return;
        }

        $this->info("🔧 Запуск сидера: {$seederClass}");
        $seeder = app(DatabaseSeeder::class);
        $seeder->runSeeder($seederClass);
    }

    /**
     * Очистка группы сидеров
     */
    private function cleanupGroup(string $groupName, bool $force): void
    {
        if (!$force && !$this->confirm("Очистить данные группы '{$groupName}'? Это действие необратимо!", false)) {
            return;
        }

        $this->warn("🧹 Очистка группы: {$groupName}");
        $seeder = app(DatabaseSeeder::class);
        $seeder->cleanupGroup($groupName);
    }

    /**
     * Показать информацию о сидерах
     */
    private function showSeederInfo(): void
    {
        $this->info('📊 Информация о сидерах');
        $this->line('');

        $seeder = app(DatabaseSeeder::class);
        $seeder->info();
    }

    /**
     * Показать доступные группы
     */
    private function showAvailableGroups(): void
    {
        $this->info('Доступные группы сидеров:');
        $groups = [
            'critical' => 'Критически важные данные',
            'infrastructure' => 'Инфраструктура системы',
            'business_logic' => 'Бизнес-логика',
            'operational_data' => 'Операционные данные',
            'analytics' => 'Аналитика и AI',
            'logs_and_archives' => 'Логи и архивы',
        ];

        foreach ($groups as $name => $description) {
            $this->line("  <comment>{$name}</comment> - {$description}");
        }
    }

    /**
     * Показать справку
     */
    private function showHelp(): void
    {
        $this->info('Использование:');
        $this->line('  php artisan seeders:manage <action> [target] [--force]');
        $this->line('');
        $this->info('Действия:');
        $this->line('  <comment>run</comment>              - Полный запуск всех сидеров');
        $this->line('  <comment>group <group></comment>     - Запуск группы сидеров');
        $this->line('  <comment>seeder <class></comment>    - Запуск отдельного сидера');
        $this->line('  <comment>cleanup <group></comment>   - Очистка данных группы');
        $this->line('  <comment>info</comment>              - Информация о сидерах');
        $this->line('');
        $this->info('Опции:');
        $this->line('  <comment>--force</comment>           - Принудительное выполнение без подтверждения');
        $this->line('');
        $this->showAvailableGroups();
    }
}
