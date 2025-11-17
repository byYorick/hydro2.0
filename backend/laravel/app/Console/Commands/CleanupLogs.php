<?php

namespace App\Console\Commands;

use Illuminate\Console\Command as ConsoleCommand;
use Illuminate\Support\Facades\DB;
use Carbon\Carbon;

class CleanupLogs extends ConsoleCommand
{
    protected $signature = 'logs:cleanup 
                            {--days=30 : Количество дней для хранения логов}';

    protected $description = 'Удаляет старые логи согласно retention policy (7-30 дней для hot logs)';

    public function handle()
    {
        $days = (int) $this->option('days');
        $cutoffDate = Carbon::now()->subDays($days);

        $this->info("Очистка логов старше {$days} дней (до {$cutoffDate->toDateTimeString()})...");

        $tables = ['system_logs', 'node_logs', 'ai_logs', 'scheduler_logs'];
        $totalDeleted = 0;

        foreach ($tables as $table) {
            $deleted = DB::table($table)
                ->where('created_at', '<', $cutoffDate)
                ->delete();
            
            $this->info("  {$table}: удалено {$deleted} записей");
            $totalDeleted += $deleted;
        }

        $this->info("Всего удалено записей: {$totalDeleted}");

        // Выполняем VACUUM для освобождения места (опционально)
        if ($this->confirm('Выполнить VACUUM для освобождения места?', false)) {
            $this->info('Выполняется VACUUM...');
            foreach ($tables as $table) {
                DB::statement("VACUUM ANALYZE {$table};");
            }
            $this->info('VACUUM завершен.');
        }

        $this->info('Очистка завершена.');
        return ConsoleCommand::SUCCESS;
    }
}

