<?php

use Illuminate\Foundation\Inspiring;
use Illuminate\Support\Facades\Artisan;
use Illuminate\Support\Facades\Schedule;
use App\Services\AutomationRuntimeConfigService;

Artisan::command('inspire', function () {
    $this->comment(Inspiring::quote());
})->purpose('Display an inspiring quote')->hourly();

// Retention политики: очистка старых raw данных (ежедневно в 2:00)
// ВНИМАНИЕ: Python telemetry-aggregator (сервис) также выполняет cleanup согласно
// RETENTION_SAMPLES_DAYS=90. Текущий дефолт --days=30 здесь означает, что реальная
// retention для telemetry_samples — 30 дней (более агрессивная политика побеждает).
// Если нужно изменить, синхронизировать с RETENTION_SAMPLES_DAYS в docker-compose.
Schedule::command('telemetry:cleanup-raw --days=30')
    ->dailyAt('02:00')
    ->description('Очистка старых raw данных телеметрии');

// Агрегация данных: каждые 15 минут
// ВНИМАНИЕ: Python telemetry-aggregator (сервис) выполняет ту же агрегацию в фоне.
// Оба используют ON CONFLICT (1m - DO UPDATE SET, Laravel - DO NOTHING), данные не дублируются.
// При наличии Python-сервиса эта команда избыточна, но безопасна.
Schedule::command('telemetry:aggregate')
    ->everyFifteenMinutes()
    ->description('Агрегация телеметрии в таблицы 1m, 1h, daily');

// Генерация прогнозов AI: каждые 15 минут
Schedule::job(new \App\Jobs\GeneratePredictionsJob())
    ->everyFifteenMinutes()
    ->description('Генерация прогнозов параметров для активных зон');

// Phase 5: Auto-revert зон с истёкшим config_mode=live TTL в locked
Schedule::command('automation:revert-expired-live-modes')
    ->everyMinute()
    ->description('Auto-revert зон с истёкшим config_mode=live TTL');

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

// Retention policies для commands и zone_events настроены через TimescaleDB/PostgreSQL
// Старые данные удаляются автоматически согласно retention policies
// Архивные таблицы удалены - используем партиционирование вместо дублей

// Очистка логов: еженедельно в воскресенье в 2:00
Schedule::command('logs:cleanup --days=30')
    ->weeklyOn(0, '02:00')
    ->description('Очистка старых логов (7-30 дней hot logs)');

// Обработка timeout команд: каждые 30 секунд
Schedule::command('commands:process-timeouts')
    ->everyThirtySeconds()
    ->description('Автоматическая обработка timeout для команд в статусе SENT');

// Автоматический replay DLQ алертов: ежедневно в 4:00
Schedule::command('alerts:dlq-replay --older-than-hours=24')
    ->dailyAt('04:00')
    ->description('Автоматический replay старых алертов из DLQ (старше 24 часов)');

// MVP cutover: перенос внешнего scheduler-dispatch в Laravel.
// Команда будит зону в automation-engine через /zones/{id}/start-cycle.
// Включается feature-flag: AUTOMATION_LARAVEL_SCHEDULER_ENABLED=true.
Schedule::command('automation:dispatch-schedules')
    ->everyMinute()
    ->withoutOverlapping(1)
    ->onOneServer()
    ->when(fn (): bool => app(AutomationRuntimeConfigService::class)->schedulerEnabled())
    ->description('Laravel scheduler dispatcher: планирование и dispatch abstract задач в automation-engine');

// Watchdog для зависших AE3 tasks: находит tasks с истёкшим stage_deadline_at или
// claimed без прогресса и помечает failed, освобождая partial unique (zone_id).
Schedule::command('ae3:reap-stale-tasks')
    ->everyMinute()
    ->withoutOverlapping(1)
    ->onOneServer()
    ->description('AE3 watchdog: reaps stale claimed/running tasks');

// Retention: ежедневно удаляет terminal ae_tasks и intents старше 90 дней,
// чтобы runtime таблицы не росли бесконечно. Audit остаётся в zone_events.
Schedule::command('ae3:cleanup-old-tasks --days=90')
    ->dailyAt('03:30')
    ->withoutOverlapping()
    ->onOneServer()
    ->description('AE3 retention: cleanup completed/failed ae_tasks and intents');

// Auto-advance recipe phases для зон в control_mode=auto. Стратегия time:
// `phase_started_at + duration_hours/days < now`. Guards: нет active task,
// нет critical/error alerts. Если последняя фаза → biz_recipe_completed_review_required.
// См. doc_ai/06_DOMAIN_ZONES_RECIPES/CONTROL_MODES_SPEC.md §4.
Schedule::command('phases:auto-advance')
    ->everyFiveMinutes()
    ->withoutOverlapping()
    ->onOneServer()
    ->description('Auto-advance recipe phases for zones in control_mode=auto');
