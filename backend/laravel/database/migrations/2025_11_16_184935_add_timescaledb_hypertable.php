<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Support\Facades\DB;

return new class extends Migration
{
    /**
     * Run the migrations.
     * Преобразует telemetry_samples в TimescaleDB hypertable для оптимизации временных рядов.
     */
    public function up(): void
    {
        // TimescaleDB работает только с PostgreSQL
        if (DB::getDriverName() !== 'pgsql') {
            return;
        }

        // Пропускаем для тестового окружения, если расширение недоступно
        if (app()->environment('testing')) {
            try {
                DB::statement("CREATE EXTENSION IF NOT EXISTS timescaledb;");
            } catch (\Exception $e) {
                // TimescaleDB недоступно в тестовом окружении - пропускаем
                return;
            }
        } else {
            // Убеждаемся, что расширение TimescaleDB установлено
            DB::statement("CREATE EXTENSION IF NOT EXISTS timescaledb;");
        }

        // Преобразуем telemetry_samples в hypertable
        // chunk_time_interval = 1 день для оптимальной производительности
        // Сначала нужно удалить primary key, так как TimescaleDB требует, чтобы partitioning column была частью primary key
        try {
            // Проверяем, не является ли таблица уже hypertable
            $isHypertable = DB::selectOne("
                SELECT EXISTS (
                    SELECT 1 FROM timescaledb_information.hypertables 
                    WHERE hypertable_name = 'telemetry_samples'
                ) as exists;
            ");
            
            if ($isHypertable && $isHypertable->exists) {
                // Уже является hypertable, пропускаем
                return;
            }
            
            // Удаляем существующий primary key
            DB::statement("ALTER TABLE telemetry_samples DROP CONSTRAINT IF EXISTS telemetry_samples_pkey;");
            
            // Создаем составной primary key с ts
            DB::statement("ALTER TABLE telemetry_samples ADD PRIMARY KEY (id, ts);");
            
            // Преобразуем в hypertable с миграцией данных, если таблица не пустая
            $rowCount = DB::selectOne("SELECT COUNT(*) as count FROM telemetry_samples")->count;
            $migrateData = $rowCount > 0;
            
            DB::statement("
                SELECT create_hypertable(
                    'telemetry_samples',
                    'ts',
                    chunk_time_interval => INTERVAL '1 day',
                    migrate_data => " . ($migrateData ? 'true' : 'false') . ",
                    if_not_exists => TRUE
                );
            ");
        } catch (\Exception $e) {
            // TimescaleDB недоступно - пропускаем создание hypertable
            if (!app()->environment('testing')) {
                throw $e;
            }
        }

        // Добавляем дополнительные индексы для оптимизации запросов
        DB::statement("
            CREATE INDEX IF NOT EXISTS telemetry_samples_sensor_ts_idx 
            ON telemetry_samples (sensor_id, ts DESC);
        ");

        DB::statement("
            CREATE INDEX IF NOT EXISTS telemetry_samples_zone_ts_idx 
            ON telemetry_samples (zone_id, ts DESC);
        ");
    }

    /**
     * Reverse the migrations.
     */
    public function down(): void
    {
        // TimescaleDB работает только с PostgreSQL
        if (DB::getDriverName() !== 'pgsql') {
            return;
        }

        // Удаляем индексы
        DB::statement("DROP INDEX IF EXISTS telemetry_samples_sensor_ts_idx;");
        DB::statement("DROP INDEX IF EXISTS telemetry_samples_zone_ts_idx;");

        // Удаляем hypertable (преобразует обратно в обычную таблицу)
        try {
            // Проверяем, является ли таблица hypertable
            $isHypertable = DB::selectOne("
                SELECT EXISTS (
                    SELECT 1 FROM timescaledb_information.hypertables 
                    WHERE hypertable_name = 'telemetry_samples'
                ) as exists;
            ");
            
            if ($isHypertable && $isHypertable->exists) {
                DB::statement("SELECT drop_hypertable('telemetry_samples', if_exists => TRUE);");
            }
        } catch (\Exception $e) {
            // Игнорируем ошибки при удалении hypertable
        }
    }
};
