<?php

namespace App\Console\Commands;

use Illuminate\Console\Command;
use Carbon\Carbon;

class BackupListCommand extends Command
{
    protected $signature = 'backup:list 
                            {--verify : Проверить целостность бэкапов}';
    
    protected $description = 'Показывает список доступных бэкапов';

    public function handle()
    {
        $backupDir = env('BACKUP_DIR', '/backups');
        
        if (!is_dir($backupDir)) {
            $this->warn("Директория бэкапов не найдена: {$backupDir}");
            return Command::SUCCESS;
        }
        
        $this->info("Директория бэкапов: {$backupDir}");
        $this->info('');
        
        // Поиск всех бэкапов
        $backups = $this->findBackups($backupDir);
        
        if (empty($backups)) {
            $this->warn('Бэкапы не найдены');
            return Command::SUCCESS;
        }
        
        // Группировка по типу
        $grouped = [];
        foreach ($backups as $backup) {
            $type = $backup['type'];
            if (!isset($grouped[$type])) {
                $grouped[$type] = [];
            }
            $grouped[$type][] = $backup;
        }
        
        // Вывод по типам
        foreach ($grouped as $type => $items) {
            $this->info("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━");
            $this->info(strtoupper($type));
            $this->info("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━");
            
            $headers = ['Дата создания', 'Размер', 'Путь'];
            $rows = [];
            
            foreach ($items as $backup) {
                $rows[] = [
                    $backup['created_at'],
                    $backup['size'],
                    $backup['path'],
                ];
            }
            
            $this->table($headers, $rows);
            $this->info('');
        }
        
        // Проверка целостности при необходимости
        if ($this->option('verify')) {
            $this->info('━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━');
            $this->info('Проверка целостности бэкапов');
            $this->info('━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━');
            
            $verified = 0;
            $failed = 0;
            
            foreach ($backups as $backup) {
                if ($this->verifyBackup($backup)) {
                    $this->info("✓ {$backup['path']}");
                    $verified++;
                } else {
                    $this->error("✗ {$backup['path']} - поврежден или недоступен");
                    $failed++;
                }
            }
            
            $this->info('');
            $this->info("Проверено: {$verified} успешно, {$failed} с ошибками");
        }
        
        return Command::SUCCESS;
    }
    
    private function findBackups($dir)
    {
        $backups = [];
        
        // Поиск в поддиректориях
        $types = ['full', 'postgres', 'laravel', 'python', 'mqtt', 'docker'];
        
        foreach ($types as $type) {
            $typeDir = $dir . '/' . $type;
            if (!is_dir($typeDir)) {
                continue;
            }
            
            $items = glob($typeDir . '/*', GLOB_ONLYDIR);
            foreach ($items as $item) {
                $manifest = $item . '/manifest.json';
                if (file_exists($manifest)) {
                    $data = json_decode(file_get_contents($manifest), true);
                    if ($data) {
                        $backups[] = [
                            'type' => $type,
                            'path' => $item,
                            'created_at' => $this->formatTimestamp($data['timestamp'] ?? ''),
                            'size' => $this->calculateDirectorySize($item),
                            'manifest' => $data,
                        ];
                    }
                }
            }
        }
        
        // Сортировка по дате (новые первыми)
        usort($backups, function ($a, $b) {
            return strcmp($b['created_at'], $a['created_at']);
        });
        
        return $backups;
    }
    
    private function formatTimestamp($timestamp)
    {
        if (empty($timestamp)) {
            return 'unknown';
        }
        
        // Попытка парсинга формата YYYYMMDD_HHMMSS
        if (preg_match('/^(\d{4})(\d{2})(\d{2})_(\d{2})(\d{2})(\d{2})$/', $timestamp, $matches)) {
            $date = Carbon::create(
                $matches[1], $matches[2], $matches[3],
                $matches[4], $matches[5], $matches[6]
            );
            return $date->format('Y-m-d H:i:s');
        }
        
        return $timestamp;
    }
    
    private function calculateDirectorySize($dir)
    {
        $size = 0;
        $files = new \RecursiveIteratorIterator(
            new \RecursiveDirectoryIterator($dir, \RecursiveDirectoryIterator::SKIP_DOTS)
        );
        
        foreach ($files as $file) {
            $size += $file->getSize();
        }
        
        return $this->formatBytes($size);
    }
    
    private function formatBytes($bytes, $precision = 2)
    {
        $units = ['B', 'KB', 'MB', 'GB', 'TB'];
        
        for ($i = 0; $bytes > 1024 && $i < count($units) - 1; $i++) {
            $bytes /= 1024;
        }
        
        return round($bytes, $precision) . ' ' . $units[$i];
    }
    
    private function verifyBackup($backup)
    {
        $path = $backup['path'];
        
        if (!is_dir($path)) {
            return false;
        }
        
        // Проверка manifest
        $manifest = $path . '/manifest.json';
        if (!file_exists($manifest)) {
            return false;
        }
        
        // Проверка наличия файлов бэкапа
        $files = glob($path . '/*');
        $hasBackupFiles = false;
        
        foreach ($files as $file) {
            if (is_file($file) && !str_ends_with($file, '.json') && !str_ends_with($file, '.log')) {
                $hasBackupFiles = true;
                // Проверка размера файла
                if (filesize($file) === 0) {
                    return false;
                }
            }
        }
        
        return $hasBackupFiles;
    }
}

