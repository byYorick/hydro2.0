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
            // Используем строгие права (0700) для предотвращения доступа через веб
            mkdir($backupDir, 0700, true);
        } else {
            // Убеждаемся, что существующая директория имеет строгие права
            chmod($backupDir, 0700);
        }

        $timestamp = Carbon::now()->format('Ymd_His');
        $filename = "postgres_{$database}_{$timestamp}.dump";
        $backupPath = $backupDir.'/'.$filename;

        // Используем .pgpass файл вместо PGPASSWORD в командной строке для безопасности
        // PGPASSWORD в командной строке виден в ps aux и может быть перехвачен
        $pgpassPath = storage_path('app/.pgpass');
        $pgpassContent = sprintf(
            "%s:%s:%s:%s:%s\n",
            $host,
            $port,
            $database,
            $username,
            $password
        );
        
        // Создаем временный .pgpass файл с строгими правами (0600)
        file_put_contents($pgpassPath, $pgpassContent);
        chmod($pgpassPath, 0600);
        
        // Устанавливаем переменную окружения для использования .pgpass
        putenv('PGPASSFILE=' . $pgpassPath);
        
        // Команда pg_dump БЕЗ PGPASSWORD в командной строке
        $command = sprintf(
            'pg_dump -h %s -p %s -U %s -d %s -Fc -f %s',
            escapeshellarg($host),
            escapeshellarg($port),
            escapeshellarg($username),
            escapeshellarg($database),
            escapeshellarg($backupPath)
        );

        $this->info("Выполнение: pg_dump для базы данных {$database}...");

        // Выполнение команды
        exec($command.' 2>&1', $output, $returnCode);
        
        // Удаляем временный .pgpass файл после использования
        if (file_exists($pgpassPath)) {
            unlink($pgpassPath);
        }

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

        // Устанавливаем строгие права на файл бэкапа (0600 - только владелец)
        chmod($backupPath, 0600);

        $fileSize = filesize($backupPath);
        $this->info("✓ Бэкап создан: {$backupPath}");
        $this->info('  Размер: '.$this->formatBytes($fileSize));

        // Сжатие при необходимости
        if ($this->option('compress')) {
            $this->info('Сжатие бэкапа...');
            $compressedPath = $backupPath.'.gz';
            exec("gzip {$backupPath}", $compressOutput, $compressReturnCode);

            if ($compressReturnCode === 0 && file_exists($compressedPath)) {
                // Устанавливаем строгие права на сжатый файл
                chmod($compressedPath, 0600);
                $compressedSize = filesize($compressedPath);
                $this->info("✓ Бэкап сжат: {$compressedPath}");
                $this->info('  Размер после сжатия: '.$this->formatBytes($compressedSize));
                $backupPath = $compressedPath;
            } else {
                $this->warn('Не удалось сжать бэкап');
            }
        }
        
        // Ротация старых бэкапов (храним только последние 7 дней)
        $this->rotateOldBackups($backupDir);

        // Сохранение информации о бэкапе БЕЗ учетных данных БД
        $manifest = [
            'timestamp' => $timestamp,
            'database' => $database,
            // НЕ включаем host, port, username, password - это чувствительные данные
            'backup_file' => basename($backupPath),
            'size_bytes' => filesize($backupPath),
            'format' => $this->option('compress') ? 'custom-compressed' : 'custom',
            'created_by' => 'DatabaseBackupCommand',
        ];

        $manifestPath = $backupDir.'/manifest_'.$timestamp.'.json';
        file_put_contents($manifestPath, json_encode($manifest, JSON_PRETTY_PRINT));
        // Устанавливаем строгие права на manifest
        chmod($manifestPath, 0600);

        $this->info("✓ Manifest создан: {$manifestPath}");
        $this->info('Бэкап базы данных завершен успешно');

        return Command::SUCCESS;
    }

    /**
     * Ротация старых бэкапов - удаление бэкапов старше 7 дней
     */
    private function rotateOldBackups(string $backupDir): void
    {
        $maxAge = 7 * 24 * 60 * 60; // 7 дней в секундах
        $now = time();
        
        $files = glob($backupDir . '/*');
        $deletedCount = 0;
        
        foreach ($files as $file) {
            if (is_file($file)) {
                $fileAge = $now - filemtime($file);
                if ($fileAge > $maxAge) {
                    unlink($file);
                    $deletedCount++;
                }
            }
        }
        
        if ($deletedCount > 0) {
            $this->info("✓ Удалено старых бэкапов: {$deletedCount}");
        }
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
