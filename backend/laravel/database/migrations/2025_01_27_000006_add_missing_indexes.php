<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;
use Illuminate\Support\Facades\DB;

return new class extends Migration
{
    /**
     * Run the migrations.
     * Добавляет недостающие индексы для оптимизации запросов.
     */
    public function up(): void
    {
        // 1. telemetry_samples - дополнительные индексы
        // Проверяем существование таблицы перед созданием индекса
        if ($this->tableExists('telemetry_samples')) {
            if (
                $this->columnExists('telemetry_samples', 'sensor_id')
                && $this->columnExists('telemetry_samples', 'ts')
                && !$this->indexExists('telemetry_samples', 'telemetry_samples_sensor_ts_idx')
            ) {
                Schema::table('telemetry_samples', function (Blueprint $table) {
                    $table->index(['sensor_id', 'ts'], 'telemetry_samples_sensor_ts_idx');
                });
            }

            if (
                $this->columnExists('telemetry_samples', 'zone_id')
                && $this->columnExists('telemetry_samples', 'ts')
                && !$this->indexExists('telemetry_samples', 'telemetry_samples_zone_ts_idx')
            ) {
                Schema::table('telemetry_samples', function (Blueprint $table) {
                    $table->index(['zone_id', 'ts'], 'telemetry_samples_zone_ts_idx');
                });
            }

            if (
                $this->columnExists('telemetry_samples', 'cycle_id')
                && $this->columnExists('telemetry_samples', 'ts')
                && !$this->indexExists('telemetry_samples', 'telemetry_samples_cycle_ts_idx')
            ) {
                Schema::table('telemetry_samples', function (Blueprint $table) {
                    $table->index(['cycle_id', 'ts'], 'telemetry_samples_cycle_ts_idx');
                });
            }

            if (
                $this->columnExists('telemetry_samples', 'ts')
                && !$this->indexExists('telemetry_samples', 'telemetry_samples_ts_idx')
            ) {
                Schema::table('telemetry_samples', function (Blueprint $table) {
                    $table->index('ts', 'telemetry_samples_ts_idx');
                });
            }

            if (
                $this->columnExists('telemetry_samples', 'quality')
                && !$this->indexExists('telemetry_samples', 'telemetry_samples_quality_idx')
            ) {
                Schema::table('telemetry_samples', function (Blueprint $table) {
                    $table->index('quality', 'telemetry_samples_quality_idx');
                });
            }
        }

        // 2. commands - дополнительные индексы
        if ($this->tableExists('commands')) {
            // Индекс для запросов по zone_id и status (часто используется вместе)
            if (!$this->indexExists('commands', 'commands_zone_status_idx')) {
                Schema::table('commands', function (Blueprint $table) {
                    $table->index(['zone_id', 'status'], 'commands_zone_status_idx');
                });
            }

            // Индекс для запросов по node_id и status
            if (!$this->indexExists('commands', 'commands_node_status_idx')) {
                Schema::table('commands', function (Blueprint $table) {
                    $table->index(['node_id', 'status'], 'commands_node_status_idx');
                });
            }

            // Индекс для запросов по created_at (для cleanup и архивации)
            if (!$this->indexExists('commands', 'commands_created_at_idx')) {
                Schema::table('commands', function (Blueprint $table) {
                    $table->index('created_at', 'commands_created_at_idx');
                });
            }

            // Индекс для запросов по sent_at (для таймаутов)
            if (!$this->indexExists('commands', 'commands_sent_at_idx')) {
                Schema::table('commands', function (Blueprint $table) {
                    $table->index('sent_at', 'commands_sent_at_idx');
                });
            }
        }

        // 3. alerts - дополнительные индексы
        if ($this->tableExists('alerts')) {
            // Индекс для запросов по type (часто используется для фильтрации)
            if (!$this->indexExists('alerts', 'alerts_type_idx')) {
                Schema::table('alerts', function (Blueprint $table) {
                    $table->index('type', 'alerts_type_idx');
                });
            }

            // Индекс для запросов по source и code (новые поля)
            if (!$this->indexExists('alerts', 'alerts_source_code_idx')) {
                Schema::table('alerts', function (Blueprint $table) {
                    $table->index(['source', 'code'], 'alerts_source_code_idx');
                });
            }

            // Индекс для запросов по created_at (для фильтрации по времени)
            if (!$this->indexExists('alerts', 'alerts_created_at_idx')) {
                Schema::table('alerts', function (Blueprint $table) {
                    $table->index('created_at', 'alerts_created_at_idx');
                });
            }

            // Индекс для запросов по resolved_at (для фильтрации разрешенных алертов)
            if (!$this->indexExists('alerts', 'alerts_resolved_at_idx')) {
                Schema::table('alerts', function (Blueprint $table) {
                    $table->index('resolved_at', 'alerts_resolved_at_idx');
                });
            }

            // Композитный индекс для zone_id, type и status (часто используется вместе)
            if (!$this->indexExists('alerts', 'alerts_zone_type_status_idx')) {
                Schema::table('alerts', function (Blueprint $table) {
                    $table->index(['zone_id', 'type', 'status'], 'alerts_zone_type_status_idx');
                });
            }

            // Композитный индекс для zone_id, code и status (для дедупликации алертов)
            if (!$this->indexExists('alerts', 'alerts_zone_code_status_idx')) {
                Schema::table('alerts', function (Blueprint $table) {
                    $table->index(['zone_id', 'code', 'status'], 'alerts_zone_code_status_idx');
                });
            }
        }

        // 4. zone_events - дополнительные индексы
        if ($this->tableExists('zone_events')) {
            // Композитный индекс для zone_id, type и created_at (часто используется вместе)
            if (!$this->indexExists('zone_events', 'zone_events_zone_type_created_idx')) {
                Schema::table('zone_events', function (Blueprint $table) {
                    $table->index(['zone_id', 'type', 'created_at'], 'zone_events_zone_type_created_idx');
                });
            }

            // Индекс для запросов только по created_at (для cleanup операций)
            if (!$this->indexExists('zone_events', 'zone_events_created_at_idx')) {
                Schema::table('zone_events', function (Blueprint $table) {
                    $table->index('created_at', 'zone_events_created_at_idx');
                });
            }
        }
    }

    /**
     * Reverse the migrations.
     */
    public function down(): void
    {
        // Удаляем индексы в обратном порядке
        Schema::table('zone_events', function (Blueprint $table) {
            $table->dropIndex('zone_events_created_at_idx');
            $table->dropIndex('zone_events_zone_type_created_idx');
        });

        Schema::table('alerts', function (Blueprint $table) {
            $table->dropIndex('alerts_zone_code_status_idx');
            $table->dropIndex('alerts_zone_type_status_idx');
            $table->dropIndex('alerts_resolved_at_idx');
            $table->dropIndex('alerts_created_at_idx');
            $table->dropIndex('alerts_source_code_idx');
            $table->dropIndex('alerts_type_idx');
        });

        Schema::table('commands', function (Blueprint $table) {
            $table->dropIndex('commands_sent_at_idx');
            $table->dropIndex('commands_created_at_idx');
            $table->dropIndex('commands_node_status_idx');
            $table->dropIndex('commands_zone_status_idx');
        });

        DB::statement("DROP INDEX IF EXISTS telemetry_samples_sensor_ts_idx;");
        DB::statement("DROP INDEX IF EXISTS telemetry_samples_zone_ts_idx;");
        DB::statement("DROP INDEX IF EXISTS telemetry_samples_cycle_ts_idx;");
        DB::statement("DROP INDEX IF EXISTS telemetry_samples_ts_idx;");
        DB::statement("DROP INDEX IF EXISTS telemetry_samples_quality_idx;");
    }

    /**
     * Проверка существования таблицы.
     */
    private function tableExists(string $table): bool
    {
        $result = DB::selectOne("
            SELECT EXISTS (
                SELECT 1 
                FROM information_schema.tables 
                WHERE table_schema = 'public' AND table_name = ?
            ) as exists
        ", [$table]);

        return $result && $result->exists;
    }

    /**
     * Проверка существования колонки.
     */
    private function columnExists(string $table, string $column): bool
    {
        $result = DB::selectOne("
            SELECT EXISTS (
                SELECT 1
                FROM information_schema.columns
                WHERE table_schema = 'public' AND table_name = ? AND column_name = ?
            ) as exists
        ", [$table, $column]);

        return $result && $result->exists;
    }

    /**
     * Проверка существования индекса.
     */
    private function indexExists(string $table, string $indexName): bool
    {
        $result = DB::selectOne("
            SELECT EXISTS (
                SELECT 1 
                FROM pg_indexes 
                WHERE tablename = ? AND indexname = ?
            ) as exists
        ", [$table, $indexName]);

        return $result && $result->exists;
    }
};
