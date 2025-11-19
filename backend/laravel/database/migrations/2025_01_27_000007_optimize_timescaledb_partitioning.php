<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Support\Facades\DB;

return new class extends Migration
{
    /**
     * Отключаем транзакции для этой миграции,
     * так как операции с TimescaleDB требуют commit.
     */
    public $withinTransaction = false;

    /**
     * Run the migrations.
     * Оптимизирует партиционирование TimescaleDB и добавляет автоматическое управление chunks.
     */
    public function up(): void
    {
        // TimescaleDB работает только с PostgreSQL
        if (DB::getDriverName() !== 'pgsql') {
            return;
        }

        try {
            // Проверяем, установлено ли расширение TimescaleDB
            $hasTimescaleDB = DB::selectOne("
                SELECT EXISTS (
                    SELECT 1 FROM pg_extension WHERE extname = 'timescaledb'
                ) as exists;
            ");

            if (!$hasTimescaleDB || !$hasTimescaleDB->exists) {
                \Log::warning('TimescaleDB extension not found, skipping partitioning optimization');
                return;
            }

            // 1. Оптимизация chunk_time_interval для telemetry_samples
            // Текущий интервал: 1 день, оставляем как есть (оптимально для наших объемов)
            // Но можно настроить retention policy для автоматического удаления старых chunks
            
            // Проверяем, является ли таблица hypertable
            $isHypertable = DB::selectOne("
                SELECT EXISTS (
                    SELECT 1 FROM timescaledb_information.hypertables 
                    WHERE hypertable_name = 'telemetry_samples'
                ) as exists;
            ");

            if ($isHypertable && $isHypertable->exists) {
                // Для telemetry_samples chunk_time_interval = 1 день (уже настроено в предыдущей миграции)
                // Это оптимальный интервал для наших объемов данных
                
                // Добавляем retention policy для автоматического удаления старых chunks
                // Удаляем chunks старше 90 дней (соответствует retention policy в aggregator)
                try {
                    DB::statement("
                        SELECT add_retention_policy(
                            'telemetry_samples',
                            INTERVAL '90 days',
                            if_not_exists => TRUE
                        );
                    ");
                    \Log::info('Added retention policy for telemetry_samples (90 days)');
                } catch (\Exception $e) {
                    // Retention policy может уже существовать
                    \Log::warning('Failed to add retention policy for telemetry_samples: ' . $e->getMessage());
                }
            }

            // 2. Оптимизация для telemetry_agg_1m
            $isHypertable1m = DB::selectOne("
                SELECT EXISTS (
                    SELECT 1 FROM timescaledb_information.hypertables 
                    WHERE hypertable_name = 'telemetry_agg_1m'
                ) as exists;
            ");

            if ($isHypertable1m && $isHypertable1m->exists) {
                // Retention policy для telemetry_agg_1m: 30 дней
                try {
                    DB::statement("
                        SELECT add_retention_policy(
                            'telemetry_agg_1m',
                            INTERVAL '30 days',
                            if_not_exists => TRUE
                        );
                    ");
                    \Log::info('Added retention policy for telemetry_agg_1m (30 days)');
                } catch (\Exception $e) {
                    \Log::warning('Failed to add retention policy for telemetry_agg_1m: ' . $e->getMessage());
                }
            }

            // 3. Оптимизация для telemetry_agg_1h
            $isHypertable1h = DB::selectOne("
                SELECT EXISTS (
                    SELECT 1 FROM timescaledb_information.hypertables 
                    WHERE hypertable_name = 'telemetry_agg_1h'
                ) as exists;
            ");

            if ($isHypertable1h && $isHypertable1h->exists) {
                // Retention policy для telemetry_agg_1h: 365 дней
                try {
                    DB::statement("
                        SELECT add_retention_policy(
                            'telemetry_agg_1h',
                            INTERVAL '365 days',
                            if_not_exists => TRUE
                        );
                    ");
                    \Log::info('Added retention policy for telemetry_agg_1h (365 days)');
                } catch (\Exception $e) {
                    \Log::warning('Failed to add retention policy for telemetry_agg_1h: ' . $e->getMessage());
                }
            }

            // 4. Настройка автоматического создания chunks (опционально)
            // TimescaleDB автоматически создает chunks, но можно настроить предварительное создание
            // Это делается через scheduled jobs в TimescaleDB (не требует миграции)

        } catch (\Exception $e) {
            \Log::warning('Failed to optimize TimescaleDB partitioning: ' . $e->getMessage());
            // Не прерываем миграцию, так как это оптимизация
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
            $hypertables = ['telemetry_samples', 'telemetry_agg_1m', 'telemetry_agg_1h'];
            
            foreach ($hypertables as $hypertable) {
                try {
                    // Получаем ID retention policy
                    $policyId = DB::selectOne("
                        SELECT job_id 
                        FROM timescaledb_information.jobs 
                        WHERE proc_name = 'policy_retention' 
                        AND hypertable_name = ?
                        LIMIT 1;
                    ", [$hypertable]);

                    if ($policyId && isset($policyId->job_id)) {
                        DB::statement("
                            SELECT remove_retention_policy(?, if_exists => TRUE);
                        ", [$hypertable]);
                    }
                } catch (\Exception $e) {
                    // Игнорируем ошибки при удалении
                }
            }
        } catch (\Exception $e) {
            \Log::warning('Failed to remove retention policies: ' . $e->getMessage());
        }
    }
};

