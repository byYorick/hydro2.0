<?php

namespace App\Console\Commands;

use Illuminate\Console\Command;
use Illuminate\Support\Facades\DB;
use Carbon\Carbon;

class TelemetryAggregateCommand extends Command
{
    /**
     * The name and signature of the console command.
     *
     * @var string
     */
    protected $signature = 'telemetry:aggregate 
                            {--from= : Начальная дата (Y-m-d H:i:s), по умолчанию последний час}
                            {--to= : Конечная дата (Y-m-d H:i:s), по умолчанию сейчас}';

    /**
     * The console command description.
     *
     * @var string
     */
    protected $description = 'Агрегирует raw данные телеметрии в таблицы 1m, 1h, daily';

    /**
     * Execute the console command.
     */
    public function handle()
    {
        $from = $this->option('from') 
            ? Carbon::parse($this->option('from'))
            : Carbon::now()->subHour();
        
        $to = $this->option('to')
            ? Carbon::parse($this->option('to'))
            : Carbon::now();

        $this->info("Агрегация данных с {$from->toDateTimeString()} по {$to->toDateTimeString()}...");

        // Агрегация по 1 минуте
        $this->info('Агрегация по 1 минуте...');
        $agg1m = DB::statement("
            INSERT INTO telemetry_agg_1m (zone_id, node_id, channel, metric_type, value_avg, value_min, value_max, value_median, sample_count, ts)
            SELECT 
                zone_id,
                node_id,
                channel,
                metric_type,
                AVG(value) as value_avg,
                MIN(value) as value_min,
                MAX(value) as value_max,
                PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY value) as value_median,
                COUNT(*) as sample_count,
                time_bucket('1 minute', ts) as ts
            FROM telemetry_samples
            WHERE ts >= ? AND ts < ?
            GROUP BY zone_id, node_id, channel, metric_type, time_bucket('1 minute', ts)
            ON CONFLICT (zone_id, node_id, channel, metric_type, ts) DO NOTHING
        ", [$from, $to]);

        $this->info('Агрегация по 1 минуте завершена.');

        // Агрегация по 1 часу (из 1m данных)
        $this->info('Агрегация по 1 часу...');
        $agg1h = DB::statement("
            INSERT INTO telemetry_agg_1h (zone_id, node_id, channel, metric_type, value_avg, value_min, value_max, value_median, sample_count, ts)
            SELECT 
                zone_id,
                node_id,
                channel,
                metric_type,
                AVG(value_avg) as value_avg,
                MIN(value_min) as value_min,
                MAX(value_max) as value_max,
                PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY value_avg) as value_median,
                SUM(sample_count) as sample_count,
                time_bucket('1 hour', ts) as ts
            FROM telemetry_agg_1m
            WHERE ts >= ? AND ts < ?
            GROUP BY zone_id, node_id, channel, metric_type, time_bucket('1 hour', ts)
            ON CONFLICT (zone_id, node_id, channel, metric_type, ts) DO NOTHING
        ", [$from, $to]);

        $this->info('Агрегация по 1 часу завершена.');

        // Агрегация по дням (из 1h данных)
        $this->info('Агрегация по дням...');
        $aggDaily = DB::statement("
            INSERT INTO telemetry_daily (zone_id, node_id, channel, metric_type, value_avg, value_min, value_max, value_median, sample_count, date)
            SELECT 
                zone_id,
                node_id,
                channel,
                metric_type,
                AVG(value_avg) as value_avg,
                MIN(value_min) as value_min,
                MAX(value_max) as value_max,
                PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY value_avg) as value_median,
                SUM(sample_count) as sample_count,
                DATE(ts) as date
            FROM telemetry_agg_1h
            WHERE ts >= ? AND ts < ?
            GROUP BY zone_id, node_id, channel, metric_type, DATE(ts)
            ON CONFLICT (zone_id, node_id, channel, metric_type, date) 
            DO UPDATE SET
                value_avg = EXCLUDED.value_avg,
                value_min = EXCLUDED.value_min,
                value_max = EXCLUDED.value_max,
                value_median = EXCLUDED.value_median,
                sample_count = EXCLUDED.sample_count
        ", [$from, $to]);

        $this->info('Агрегация по дням завершена.');
        $this->info('Агрегация завершена.');
        
        return Command::SUCCESS;
    }
}
