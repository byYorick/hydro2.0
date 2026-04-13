<?php

namespace App\Console\Commands;

use Carbon\Carbon;
use Illuminate\Console\Command;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Log;

/**
 * Retention policy для AE3 runtime таблиц.
 *
 * Удаляет terminal записи старше заданного порога (по умолчанию 90 дней):
 *  - `ae_tasks` в статусах `completed`, `failed`, `cancelled`, `timeout`, `expired`
 *  - `zone_automation_intents` в тех же terminal-статусах
 *
 * Активные записи (pending/claimed/running/waiting_command) НЕ трогаем.
 * Индексы по `updated_at`/`completed_at` в БД делают DELETE эффективным.
 *
 * Историческая информация о циклах хранится в `zone_events` (retention 180 дней
 * по политике `DATA_RETENTION_POLICY.md`) — этого достаточно для audit, а
 * runtime таблицы не должны расти бесконечно.
 */
class Ae3CleanupOldTasks extends Command
{
    protected $signature = 'ae3:cleanup-old-tasks {--days=90 : Сколько дней хранить terminal записи}';

    protected $description = 'Удаляет старые completed/failed/cancelled ae_tasks и intents';

    private const TERMINAL_TASK_STATUSES = ['completed', 'failed', 'cancelled', 'timeout', 'expired'];
    private const TERMINAL_INTENT_STATUSES = ['completed', 'failed', 'cancelled', 'expired'];

    public function handle(): int
    {
        $days = max(1, (int) $this->option('days'));
        $cutoff = Carbon::now('UTC')->subDays($days)->setMicroseconds(0);

        $tasksDeleted = DB::table('ae_tasks')
            ->whereIn('status', self::TERMINAL_TASK_STATUSES)
            ->where('updated_at', '<', $cutoff)
            ->delete();

        $intentsDeleted = DB::table('zone_automation_intents')
            ->whereIn('status', self::TERMINAL_INTENT_STATUSES)
            ->where('updated_at', '<', $cutoff)
            ->delete();

        $total = $tasksDeleted + $intentsDeleted;
        if ($total > 0) {
            Log::info('AE3 retention cleanup completed', [
                'cutoff' => $cutoff->toIso8601String(),
                'days' => $days,
                'ae_tasks_deleted' => $tasksDeleted,
                'intents_deleted' => $intentsDeleted,
            ]);
            $this->info("Deleted {$tasksDeleted} ae_tasks and {$intentsDeleted} intents older than {$days} days");
        } else {
            $this->info("No terminal records older than {$days} days found");
        }

        return self::SUCCESS;
    }
}
