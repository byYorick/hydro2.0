<?php

use Illuminate\Foundation\Inspiring;
use Illuminate\Support\Facades\Artisan;
use Illuminate\Support\Facades\Schedule;

Artisan::command('inspire', function () {
    $this->comment(Inspiring::quote());
})->purpose('Display an inspiring quote')->hourly();

// Retention политики: очистка старых raw данных (ежедневно в 2:00)
Schedule::command('telemetry:cleanup-raw --days=30')
    ->dailyAt('02:00')
    ->description('Очистка старых raw данных телеметрии');

// Агрегация данных: каждые 15 минут
Schedule::command('telemetry:aggregate')
    ->everyFifteenMinutes()
    ->description('Агрегация телеметрии в таблицы 1m, 1h, daily');

// Генерация прогнозов AI: каждые 15 минут
Schedule::job(new \App\Jobs\GeneratePredictionsJob())
    ->everyFifteenMinutes()
    ->description('Генерация прогнозов параметров для активных зон');

// Полный бэкап системы: ежедневно в 3:00
Schedule::command('backup:full')
    ->dailyAt('03:00')
    ->description('Полный бэкап всех компонентов системы')
    ->onFailure(function () {
        \Log::error('Ошибка при создании полного бэкапа');
    });

// Ротация бэкапов: ежедневно в 3:30 (после создания бэкапа)
Schedule::call(function () {
    $scriptPath = base_path('../scripts/backup/rotate_backups.sh');
    if (file_exists($scriptPath)) {
        $backupDir = env('BACKUP_DIR', '/backups');
        $process = \Illuminate\Support\Facades\Process::path(base_path('..'))
            ->env(['BACKUP_DIR' => $backupDir])
            ->timeout(600)
            ->run("bash {$scriptPath}");
        
        if (!$process->successful()) {
            \Log::error('Ошибка при ротации бэкапов: ' . $process->errorOutput());
        }
    }
})
    ->dailyAt('03:30')
    ->description('Ротация старых бэкапов (удаление старше 30 дней)');
