<?php

namespace App\Console\Commands;

use Illuminate\Console\Command;
use Illuminate\Support\Facades\Process;

class FullBackupCommand extends Command
{
    protected $signature = 'backup:full 
                            {--skip-docker : Пропустить бэкап Docker volumes}
                            {--skip-mqtt : Пропустить бэкап MQTT конфигураций}';

    protected $description = 'Создает полный бэкап всех компонентов системы';

    public function handle()
    {
        $this->info('━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━');
        $this->info('Создание полного бэкапа системы');
        $this->info('━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━');

        $scriptDir = config('backup.script_directory');
        $fullBackupScript = $scriptDir.'/full_backup.sh';

        // Проверка существования скрипта
        if (! file_exists($fullBackupScript)) {
            $this->error("Скрипт полного бэкапа не найден: {$fullBackupScript}");

            return Command::FAILURE;
        }

        // Подготовка переменных окружения
        $backupDir = config('backup.directory');
        $skipDocker = $this->option('skip-docker') || ! config('backup.include_docker_volumes');
        $env = [
            'BACKUP_DIR' => $backupDir,
            'LARAVEL_DIR' => base_path(),
            'SERVICES_DIR' => config('backup.services_directory'),
            'MQTT_CONFIG_DIR' => config('backup.mqtt_directory'),
            'CONFIGS_DIR' => config('backup.configs_directory'),
            'DEPLOY_ENV_FILE' => config('backup.env_file'),
            'DEPLOY_COMPOSE_FILE' => config('backup.compose_file'),
            'ACTIVE_APP_KEY' => config('app.key'),
            'DB_HOST' => config('database.connections.pgsql.host'),
            'DB_PORT' => (string) config('database.connections.pgsql.port'),
            'DB_NAME' => config('database.connections.pgsql.database'),
            'DB_USER' => config('database.connections.pgsql.username'),
            'DB_PASSWORD' => config('database.connections.pgsql.password'),
            'SKIP_DOCKER' => $skipDocker ? '1' : '0',
            'SKIP_MQTT' => $this->option('skip-mqtt') ? '1' : '0',
        ];

        // Добавление опций в переменные окружения
        if ($skipDocker) {
            $this->warn('Пропуск бэкапа Docker volumes');
        }

        if ($this->option('skip-mqtt')) {
            $this->warn('Пропуск бэкапа MQTT конфигураций');
        }

        // Выполнение скрипта
        $this->info("Запуск скрипта: {$fullBackupScript}");
        $this->info("Директория бэкапов: {$backupDir}");

        $process = Process::path(base_path('..'))
            ->env($env)
            ->timeout(3600) // 1 час таймаут
            ->run(['bash', $fullBackupScript]);

        if ($process->successful()) {
            $output = $process->output();
            $this->info($output);

            // Попытка извлечь путь к созданному бэкапу
            $lines = explode("\n", $output);
            $backupPath = null;
            foreach ($lines as $line) {
                if (strpos($line, '/backups/full/') !== false || strpos($line, $backupDir) !== false) {
                    $backupPath = trim($line);
                    break;
                }
            }

            if ($backupPath) {
                $this->info('━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━');
                $this->info('✓ Полный бэкап создан успешно');
                $this->info("  Директория: {$backupPath}");
                $this->info('━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━');
            } else {
                $this->info('✓ Полный бэкап создан успешно');
            }

            return Command::SUCCESS;
        } else {
            $this->error('Ошибка при создании полного бэкапа:');
            $this->error($process->errorOutput());

            return Command::FAILURE;
        }
    }
}
