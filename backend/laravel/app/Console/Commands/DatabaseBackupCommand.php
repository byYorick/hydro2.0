<?php

namespace App\Console\Commands;

use Carbon\Carbon;
use Illuminate\Console\Command;
use Illuminate\Support\Facades\DB;

class DatabaseBackupCommand extends Command
{
    protected $signature = 'backup:database 
                            {--compress : Сжать дамп после создания}
                            {--output= : Путь для сохранения бэкапа}';

    protected $description = 'Создает полный дамп базы данных PostgreSQL';

    public function handle()
    {
        $this->info('Создание бэкапа базы данных...');

        // Получение параметров подключения
        $host = config('database.connections.pgsql.host');
        $port = config('database.connections.pgsql.port');
        $database = config('database.connections.pgsql.database');
        $username = config('database.connections.pgsql.username');
        $password = config('database.connections.pgsql.password');

        // Проверка подключения
        try {
            DB::connection('pgsql')->getPdo();
        } catch (\Exception $e) {
            $this->error('Не удалось подключиться к базе данных: '.$e->getMessage());

            return Command::FAILURE;
        }

        // Определение пути для сохранения
        $backupDir = $this->option('output')
            ? dirname($this->option('output'))
            : storage_path('app/private/backups');

        if (! is_dir($backupDir)) {
            mkdir($backupDir, 0755, true);
        }

        $timestamp = Carbon::now()->format('Ymd_His');
        $filename = "postgres_{$database}_{$timestamp}.dump";
        $backupPath = $backupDir.'/'.$filename;

        // Команда pg_dump
        $command = sprintf(
            'PGPASSWORD=%s pg_dump -h %s -p %s -U %s -d %s -Fc -f %s',
            escapeshellarg($password),
            escapeshellarg($host),
            escapeshellarg($port),
            escapeshellarg($username),
            escapeshellarg($database),
            escapeshellarg($backupPath)
        );

        $this->info("Выполнение: pg_dump для базы данных {$database}...");

        // Выполнение команды
        exec($command.' 2>&1', $output, $returnCode);

        if ($returnCode !== 0) {
            $this->error('Ошибка при создании бэкапа:');
            $this->error(implode("\n", $output));

            return Command::FAILURE;
        }

        // Проверка существования файла
        if (! file_exists($backupPath)) {
            $this->error('Файл бэкапа не был создан');

            return Command::FAILURE;
        }

        $fileSize = filesize($backupPath);
        $this->info("✓ Бэкап создан: {$backupPath}");
        $this->info('  Размер: '.$this->formatBytes($fileSize));

        // Сжатие при необходимости
        if ($this->option('compress')) {
            $this->info('Сжатие бэкапа...');
            $compressedPath = $backupPath.'.gz';
            exec("gzip {$backupPath}", $compressOutput, $compressReturnCode);

            if ($compressReturnCode === 0 && file_exists($compressedPath)) {
                $compressedSize = filesize($compressedPath);
                $this->info("✓ Бэкап сжат: {$compressedPath}");
                $this->info('  Размер после сжатия: '.$this->formatBytes($compressedSize));
                $backupPath = $compressedPath;
            } else {
                $this->warn('Не удалось сжать бэкап');
            }
        }

        // Сохранение информации о бэкапе
        $manifest = [
            'timestamp' => $timestamp,
            'database' => $database,
            'host' => $host,
            'port' => $port,
            'backup_file' => basename($backupPath),
            'size_bytes' => filesize($backupPath),
            'format' => $this->option('compress') ? 'custom-compressed' : 'custom',
            'created_by' => 'DatabaseBackupCommand',
        ];

        $manifestPath = $backupDir.'/manifest_'.$timestamp.'.json';
        file_put_contents($manifestPath, json_encode($manifest, JSON_PRETTY_PRINT));

        $this->info("✓ Manifest создан: {$manifestPath}");
        $this->info('Бэкап базы данных завершен успешно');

        return Command::SUCCESS;
    }

    private function formatBytes($bytes, $precision = 2)
    {
        $units = ['B', 'KB', 'MB', 'GB', 'TB'];

        for ($i = 0; $bytes > 1024 && $i < count($units) - 1; $i++) {
            $bytes /= 1024;
        }

        return round($bytes, $precision).' '.$units[$i];
    }
}
