<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;
use Illuminate\Support\Facades\DB;

return new class extends Migration
{
    /**
     * Run the migrations.
     * 
     * Добавляет недостающие индексы для таблиц nodes, telemetry_last, commands
     * для оптимизации запросов в PostgreSQL.
     */
    public function up(): void
    {
        // 1. Индексы для таблицы nodes
        if ($this->tableExists('nodes')) {
            // Индекс для запросов по zone_id (часто используется для получения узлов зоны)
            if (!$this->indexExists('nodes', 'nodes_zone_id_idx')) {
                DB::statement("CREATE INDEX nodes_zone_id_idx ON nodes (zone_id) WHERE zone_id IS NOT NULL");
            }

            // Композитный индекс для zone_id + type (часто используется вместе)
            if (!$this->indexExists('nodes', 'nodes_zone_type_idx')) {
                DB::statement("CREATE INDEX nodes_zone_type_idx ON nodes (zone_id, type) WHERE zone_id IS NOT NULL AND type IS NOT NULL");
            }

            // Композитный индекс для zone_id + status (для получения online узлов зоны)
            if (!$this->indexExists('nodes', 'nodes_zone_status_idx')) {
                DB::statement("CREATE INDEX nodes_zone_status_idx ON nodes (zone_id, status) WHERE zone_id IS NOT NULL");
            }

            // Индекс для last_seen_at (для cleanup операций и мониторинга)
            if (!$this->indexExists('nodes', 'nodes_last_seen_at_idx')) {
                DB::statement("CREATE INDEX nodes_last_seen_at_idx ON nodes (last_seen_at) WHERE last_seen_at IS NOT NULL");
            }

            // Индекс для type (для фильтрации по типу узла)
            if (!$this->indexExists('nodes', 'nodes_type_idx')) {
                DB::statement("CREATE INDEX nodes_type_idx ON nodes (type) WHERE type IS NOT NULL");
            }
        }

        // 2. Индексы для таблицы telemetry_last
        if ($this->tableExists('telemetry_last')) {
            // Индекс для node_id (для получения телеметрии конкретного узла)
            if (!$this->indexExists('telemetry_last', 'telemetry_last_node_id_idx')) {
                DB::statement("CREATE INDEX telemetry_last_node_id_idx ON telemetry_last (node_id) WHERE node_id IS NOT NULL");
            }

            // Композитный индекс для zone_id + node_id (часто используется вместе)
            if (!$this->indexExists('telemetry_last', 'telemetry_last_zone_node_idx')) {
                DB::statement("CREATE INDEX telemetry_last_zone_node_idx ON telemetry_last (zone_id, node_id) WHERE node_id IS NOT NULL");
            }

            // Индекс для updated_at (для проверки свежести данных)
            if (!$this->indexExists('telemetry_last', 'telemetry_last_updated_at_idx')) {
                DB::statement("CREATE INDEX telemetry_last_updated_at_idx ON telemetry_last (updated_at) WHERE updated_at IS NOT NULL");
            }

            // Композитный индекс для zone_id + metric_type (для быстрого поиска по метрике в зоне)
            if (!$this->indexExists('telemetry_last', 'telemetry_last_zone_metric_idx')) {
                DB::statement("CREATE INDEX telemetry_last_zone_metric_idx ON telemetry_last (zone_id, metric_type)");
            }
        }

        // 3. Дополнительные индексы для таблицы commands
        if ($this->tableExists('commands')) {
            // Композитный индекс для zone_id + node_id + status (часто используется вместе)
            if (!$this->indexExists('commands', 'commands_zone_node_status_idx')) {
                DB::statement("CREATE INDEX commands_zone_node_status_idx ON commands (zone_id, node_id, status) WHERE zone_id IS NOT NULL AND node_id IS NOT NULL");
            }

            // Индекс для ack_at (для проверки подтвержденных команд)
            if (!$this->indexExists('commands', 'commands_ack_at_idx')) {
                DB::statement("CREATE INDEX commands_ack_at_idx ON commands (ack_at) WHERE ack_at IS NOT NULL");
            }

            // Композитный индекс для node_id + channel (для поиска команд по узлу и каналу)
            if (!$this->indexExists('commands', 'commands_node_channel_idx')) {
                DB::statement("CREATE INDEX commands_node_channel_idx ON commands (node_id, channel) WHERE node_id IS NOT NULL AND channel IS NOT NULL");
            }
        }
    }

    /**
     * Reverse the migrations.
     */
    public function down(): void
    {
        // Удаляем индексы в обратном порядке
        if ($this->tableExists('commands')) {
            DB::statement("DROP INDEX IF EXISTS commands_node_channel_idx");
            DB::statement("DROP INDEX IF EXISTS commands_ack_at_idx");
            DB::statement("DROP INDEX IF EXISTS commands_zone_node_status_idx");
        }

        if ($this->tableExists('telemetry_last')) {
            DB::statement("DROP INDEX IF EXISTS telemetry_last_zone_metric_idx");
            DB::statement("DROP INDEX IF EXISTS telemetry_last_updated_at_idx");
            DB::statement("DROP INDEX IF EXISTS telemetry_last_zone_node_idx");
            DB::statement("DROP INDEX IF EXISTS telemetry_last_node_id_idx");
        }

        if ($this->tableExists('nodes')) {
            DB::statement("DROP INDEX IF EXISTS nodes_type_idx");
            DB::statement("DROP INDEX IF EXISTS nodes_last_seen_at_idx");
            DB::statement("DROP INDEX IF EXISTS nodes_zone_status_idx");
            DB::statement("DROP INDEX IF EXISTS nodes_zone_type_idx");
            DB::statement("DROP INDEX IF EXISTS nodes_zone_id_idx");
        }
    }

    /**
     * Проверка существования таблицы.
     */
    private function tableExists(string $table): bool
    {
        // Проверяем, что это PostgreSQL
        if (DB::getDriverName() !== 'pgsql') {
            return false;
        }

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
     * Проверка существования индекса.
     */
    private function indexExists(string $table, string $indexName): bool
    {
        // Проверяем, что это PostgreSQL
        if (DB::getDriverName() !== 'pgsql') {
            return false;
        }

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
