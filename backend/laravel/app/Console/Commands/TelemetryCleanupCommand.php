<?php

namespace App\Console\Commands;

use Illuminate\Console\Command;
use Illuminate\Support\Facades\DB;
use Carbon\Carbon;

class TelemetryCleanupCommand extends Command
{
    /**
     * The name and signature of the console command.
     *
     * @var string
     */
    protected $signature = 'telemetry:cleanup-raw 
                            {--days=30 : Количество дней для хранения raw данных}';

    /**
     * The console command description.
     *
     * @var string
     */
    protected $description = 'Удаляет старые raw данные телеметрии согласно retention policy';

    /**
     * Execute the console command.
     */
    public function handle()
    {
        $days = (int) $this->option('days');
        $cutoffDate = Carbon::now()->subDays($days);

        $this->info("Очистка raw данных телеметрии старше {$days} дней (до {$cutoffDate->toDateTimeString()})...");

        // Удаляем старые записи из telemetry_samples
        $deleted = DB::table('telemetry_samples')
            ->where('ts', '<', $cutoffDate)
            ->delete();

        $this->info("Удалено записей: {$deleted}");

        // Выполняем VACUUM для освобождения места (опционально, может быть медленным)
        if ($this->confirm('Выполнить VACUUM для освобождения места?', false)) {
            $this->info('Выполняется VACUUM...');
            DB::statement('VACUUM ANALYZE telemetry_samples;');
            $this->info('VACUUM завершен.');
        }

        $this->info('Очистка завершена.');
        return Command::SUCCESS;
    }
}
