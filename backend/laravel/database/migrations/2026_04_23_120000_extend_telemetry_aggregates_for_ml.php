<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    /**
     * ML_FEATURE_PIPELINE Phase 1: расширение telemetry_agg_1m и telemetry_agg_1h
     * полями для обучения моделей прогноза и детекции аномалий.
     *
     * См. doc_ai/09_AI_AND_DIGITAL_TWIN/ML_FEATURE_PIPELINE.md §5.1 и Приложение C.
     */
    public function up(): void
    {
        foreach (['telemetry_agg_1m', 'telemetry_agg_1h'] as $table) {
            if (!Schema::hasTable($table)) {
                continue;
            }

            $columns = [
                'value_std'      => 'double precision',
                'value_p10'      => 'double precision',
                'value_p90'      => 'double precision',
                'slope_per_min'  => 'double precision',
                'valid_count'    => 'integer',
                'agg_version'    => 'smallint',
            ];

            foreach ($columns as $name => $type) {
                if (!Schema::hasColumn($table, $name)) {
                    $default = match ($name) {
                        'valid_count' => 'DEFAULT 0',
                        'agg_version' => 'NOT NULL DEFAULT 1',
                        default       => '',
                    };
                    DB::statement("ALTER TABLE {$table} ADD COLUMN {$name} {$type} {$default}");
                }
            }
        }

        // Compression policy для telemetry_agg_1m: сжимать чанки старше 14 дней.
        // telemetry_agg_1h оставляем без compression (уже часовые данные, мало строк).
        if (DB::getDriverName() === 'pgsql' && !app()->environment('testing')) {
            try {
                $isHypertable = DB::selectOne("
                    SELECT EXISTS (
                        SELECT 1 FROM timescaledb_information.hypertables
                        WHERE hypertable_name = 'telemetry_agg_1m'
                    ) AS exists
                ");

                if ($isHypertable && $isHypertable->exists) {
                    // Включаем compression (идемпотентно)
                    DB::statement("
                        ALTER TABLE telemetry_agg_1m SET (
                            timescaledb.compress,
                            timescaledb.compress_segmentby = 'zone_id, metric_type'
                        )
                    ");

                    // Policy добавляется один раз — проверяем наличие
                    $hasPolicy = DB::selectOne("
                        SELECT EXISTS (
                            SELECT 1 FROM timescaledb_information.jobs
                            WHERE proc_name = 'policy_compression'
                              AND hypertable_name = 'telemetry_agg_1m'
                        ) AS exists
                    ");

                    if (!$hasPolicy || !$hasPolicy->exists) {
                        DB::statement("
                            SELECT add_compression_policy(
                                'telemetry_agg_1m',
                                INTERVAL '14 days',
                                if_not_exists => TRUE
                            )
                        ");
                    }
                }
            } catch (\Exception $e) {
                \Log::warning('ML Phase 1: failed to enable compression on telemetry_agg_1m: ' . $e->getMessage());
            }
        }
    }

    public function down(): void
    {
        if (DB::getDriverName() === 'pgsql' && !app()->environment('testing')) {
            try {
                DB::statement("SELECT remove_compression_policy('telemetry_agg_1m', if_exists => TRUE)");
            } catch (\Exception $e) {
                // ignore
            }
            try {
                DB::statement("ALTER TABLE telemetry_agg_1m SET (timescaledb.compress = false)");
            } catch (\Exception $e) {
                // ignore — compression может быть не включён
            }
        }

        foreach (['telemetry_agg_1m', 'telemetry_agg_1h'] as $table) {
            if (!Schema::hasTable($table)) {
                continue;
            }
            foreach (['agg_version', 'valid_count', 'slope_per_min', 'value_p90', 'value_p10', 'value_std'] as $col) {
                if (Schema::hasColumn($table, $col)) {
                    DB::statement("ALTER TABLE {$table} DROP COLUMN {$col}");
                }
            }
        }
    }
};
