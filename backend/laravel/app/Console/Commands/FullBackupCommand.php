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
        
        $scriptDir = base_path('../scripts/backup');
        $fullBackupScript = $scriptDir . '/full_backup.sh';
        
        // Проверка существования скрипта
        if (!file_exists($fullBackupScript)) {
            $this->error("Скрипт полного бэкапа не найден: {$fullBackupScript}");
            return Command::FAILURE;
        }
        
        // Подготовка переменных окружения
        $backupDir = env('BACKUP_DIR', '/backups');
        $env = [
            'BACKUP_DIR' => $backupDir,
        ];
        
        // Добавление опций в переменные окружения
        if ($this->option('skip-docker')) {
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
            ->run("bash {$fullBackupScript}");
        
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
                $this->info("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━");
                $this->info("✓ Полный бэкап создан успешно");
                $this->info("  Директория: {$backupPath}");
                $this->info("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━");
            } else {
                $this->info("✓ Полный бэкап создан успешно");
            }
            
            return Command::SUCCESS;
        } else {
            $this->error('Ошибка при создании полного бэкапа:');
            $this->error($process->errorOutput());
            return Command::FAILURE;
        }
    }
}

