<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    /**
     * Run the migrations.
     * 
     * Настройка партиционирования и retention policies для commands и zone_events.
     * Вместо архивных таблиц используем партиционирование по времени и автоматическое удаление старых данных.
     */
    public function up(): void
    {
        // Проверяем, что используется PostgreSQL
        if (DB::getDriverName() !== 'pgsql') {
            return;
        }

        try {
            // 1. Партиционирование для commands по created_at (ежемесячные партиции)
            if (Schema::hasTable('commands')) {
                // Проверяем, не является ли таблица уже партиционированной
                $isPartitioned = DB::selectOne("
                    SELECT EXISTS (
                        SELECT 1 FROM pg_inherits 
                        WHERE inhrelid = 'commands'::regclass
                    ) as is_partitioned
                ");

                if (!$isPartitioned || !$isPartitioned->is_partitioned) {
                    // Создаем партиционированную таблицу
                    // Для PostgreSQL 10+ используем native partitioning
                    DB::statement("
                        -- Создаем новую партиционированную таблицу
                        CREATE TABLE IF NOT EXISTS commands_partitioned (
                            LIKE commands INCLUDING ALL
                        ) PARTITION BY RANGE (created_at);
                    ");

                    // Создаем партиции на год вперед (по месяцам)
                    $this->createMonthlyPartitions('commands_partitioned', 'commands', 'created_at', 12);

                    // Копируем данные из старой таблицы
                    DB::statement("
                        INSERT INTO commands_partitioned 
                        SELECT * FROM commands;
                    ");

                    // Переименовываем таблицы
                    DB::statement("ALTER TABLE commands RENAME TO commands_old");
                    DB::statement("ALTER TABLE commands_partitioned RENAME TO commands");

                    // Удаляем старую таблицу
                    DB::statement("DROP TABLE commands_old CASCADE");

                    \Log::info('Partitioned commands table by created_at (monthly partitions)');
                }
            }

            // 2. Партиционирование для zone_events по created_at (ежемесячные партиции)
            if (Schema::hasTable('zone_events')) {
                $isPartitioned = DB::selectOne("
                    SELECT EXISTS (
                        SELECT 1 FROM pg_inherits 
                        WHERE inhrelid = 'zone_events'::regclass
                    ) as is_partitioned
                ");

                if (!$isPartitioned || !$isPartitioned->is_partitioned) {
                    DB::statement("
                        CREATE TABLE IF NOT EXISTS zone_events_partitioned (
                            LIKE zone_events INCLUDING ALL
                        ) PARTITION BY RANGE (created_at);
                    ");

                    $this->createMonthlyPartitions('zone_events_partitioned', 'zone_events', 'created_at', 12);

                    DB::statement("
                        INSERT INTO zone_events_partitioned 
                        SELECT * FROM zone_events;
                    ");

                    DB::statement("ALTER TABLE zone_events RENAME TO zone_events_old");
                    DB::statement("ALTER TABLE zone_events_partitioned RENAME TO zone_events");
                    DB::statement("DROP TABLE zone_events_old CASCADE");

                    \Log::info('Partitioned zone_events table by created_at (monthly partitions)');
                }
            }

            // 3. Retention policies через PostgreSQL (если TimescaleDB не используется)
            // Для commands: удаляем данные старше 365 дней
            $this->createRetentionPolicy('commands', 'created_at', 365);
            
            // Для zone_events: удаляем данные старше 365 дней
            $this->createRetentionPolicy('zone_events', 'created_at', 365);

            // 4. Если используется TimescaleDB, добавляем retention policies через TimescaleDB
            $hasTimescaleDB = DB::selectOne("
                SELECT EXISTS (
                    SELECT 1 FROM pg_extension WHERE extname = 'timescaledb'
                ) as exists
            ");

            if ($hasTimescaleDB && $hasTimescaleDB->exists) {
                // Проверяем, являются ли таблицы hypertables
                $isCommandsHypertable = DB::selectOne("
                    SELECT EXISTS (
                        SELECT 1 FROM timescaledb_information.hypertables 
                        WHERE hypertable_name = 'commands'
                    ) as exists
                ");

                if (!$isCommandsHypertable || !$isCommandsHypertable->exists) {
                    // Преобразуем в hypertable для TimescaleDB
                    try {
                        DB::statement("SELECT create_hypertable('commands', 'created_at', chunk_time_interval => INTERVAL '1 month')");
                        \Log::info('Converted commands to TimescaleDB hypertable');
                    } catch (\Exception $e) {
                        \Log::warning('Failed to convert commands to hypertable: ' . $e->getMessage());
                    }
                }

                $isEventsHypertable = DB::selectOne("
                    SELECT EXISTS (
                        SELECT 1 FROM timescaledb_information.hypertables 
                        WHERE hypertable_name = 'zone_events'
                    ) as exists
                ");

                if (!$isEventsHypertable || !$isEventsHypertable->exists) {
                    try {
                        DB::statement("SELECT create_hypertable('zone_events', 'created_at', chunk_time_interval => INTERVAL '1 month')");
                        \Log::info('Converted zone_events to TimescaleDB hypertable');
                    } catch (\Exception $e) {
                        \Log::warning('Failed to convert zone_events to hypertable: ' . $e->getMessage());
                    }
                }

                // Добавляем retention policies через TimescaleDB
                try {
                    DB::statement("
                        SELECT add_retention_policy(
                            'commands',
                            INTERVAL '365 days',
                            if_not_exists => TRUE
                        );
                    ");
                    \Log::info('Added TimescaleDB retention policy for commands (365 days)');
                } catch (\Exception $e) {
                    \Log::warning('Failed to add retention policy for commands: ' . $e->getMessage());
                }

                try {
                    DB::statement("
                        SELECT add_retention_policy(
                            'zone_events',
                            INTERVAL '365 days',
                            if_not_exists => TRUE
                        );
                    ");
                    \Log::info('Added TimescaleDB retention policy for zone_events (365 days)');
                } catch (\Exception $e) {
                    \Log::warning('Failed to add retention policy for zone_events: ' . $e->getMessage());
                }
            }

        } catch (\Exception $e) {
            \Log::warning('Failed to setup partitioning and retention: ' . $e->getMessage());
            // Не прерываем миграцию, так как это оптимизация
        }
    }

    /**
     * Создает ежемесячные партиции для таблицы
     */
    private function createMonthlyPartitions(string $tableName, string $sourceTable, string $dateColumn, int $monthsAhead): void
    {
        $startDate = now()->startOfMonth();
        
        for ($i = -1; $i <= $monthsAhead; $i++) {
            $partitionStart = $startDate->copy()->addMonths($i);
            $partitionEnd = $partitionStart->copy()->addMonth();
            $partitionName = $tableName . '_' . $partitionStart->format('Y_m');
            
            try {
                DB::statement("
                    CREATE TABLE IF NOT EXISTS {$partitionName} 
                    PARTITION OF {$tableName}
                    FOR VALUES FROM ('{$partitionStart->toDateString()}') TO ('{$partitionEnd->toDateString()}');
                ");
            } catch (\Exception $e) {
                \Log::warning("Failed to create partition {$partitionName}: " . $e->getMessage());
            }
        }
    }

    /**
     * Создает retention policy через PostgreSQL (без TimescaleDB)
     */
    private function createRetentionPolicy(string $tableName, string $dateColumn, int $days): void
    {
        // Создаем функцию для автоматического удаления старых данных
        $functionName = "retention_policy_{$tableName}";
        
        try {
            DB::statement("
                CREATE OR REPLACE FUNCTION {$functionName}()
                RETURNS void AS $$
                BEGIN
                    DELETE FROM {$tableName} 
                    WHERE {$dateColumn} < NOW() - INTERVAL '{$days} days';
                END;
                $$ LANGUAGE plpgsql;
            ");

            // Создаем scheduled job (требует pg_cron extension)
            // Если pg_cron не установлен, это будет проигнорировано
            try {
                DB::statement("
                    SELECT cron.schedule(
                        'retention-{$tableName}',
                        '0 2 * * *', -- Ежедневно в 2:00
                        'SELECT {$functionName}();'
                    );
                ");
                \Log::info("Created retention policy function and cron job for {$tableName}");
            } catch (\Exception $e) {
                \Log::info("pg_cron not available, retention policy function created but not scheduled: " . $e->getMessage());
            }
        } catch (\Exception $e) {
            \Log::warning("Failed to create retention policy for {$tableName}: " . $e->getMessage());
        }
    }

    /**
     * Reverse the migrations.
     */
    public function down(): void
    {
        if (DB::getDriverName() !== 'pgsql') {
            return;
        }

        try {
            // Удаляем retention policies
            $tables = ['commands', 'zone_events'];
            
            foreach ($tables as $table) {
                try {
                    // Удаляем TimescaleDB retention policies
                    DB::statement("
                        SELECT remove_retention_policy('{$table}', if_exists => TRUE);
                    ");
                } catch (\Exception $e) {
                    // Игнорируем ошибки
                }

                // Удаляем функции retention policy
                try {
                    DB::statement("DROP FUNCTION IF EXISTS retention_policy_{$table}() CASCADE");
                } catch (\Exception $e) {
                    // Игнорируем ошибки
                }

                // Удаляем cron jobs
                try {
                    DB::statement("SELECT cron.unschedule('retention-{$table}')");
                } catch (\Exception $e) {
                    // Игнорируем ошибки
                }
            }
        } catch (\Exception $e) {
            \Log::warning('Failed to remove retention policies: ' . $e->getMessage());
        }
    }
};
