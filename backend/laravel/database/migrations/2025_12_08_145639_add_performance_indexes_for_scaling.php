<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;
use Illuminate\Support\Facades\DB;

return new class extends Migration
{
    /**
     * Run the migrations.
     * Добавляет индексы для масштабирования до 10-20 теплиц (50-100 зон).
     */
    public function up(): void
    {
        // 1. nodes - композитные индексы для частых запросов
        if ($this->tableExists('nodes')) {
            // Индекс для запросов по zone_id, uid, hardware_id, status, lifecycle_state
            // Используется в NodeController::index, NodeService::update, NodeRegistryService
            if (!$this->indexExists('nodes', 'nodes_zone_uid_hardware_status_lifecycle_idx')) {
                DB::statement("
                    CREATE INDEX nodes_zone_uid_hardware_status_lifecycle_idx 
                    ON nodes (zone_id, uid, hardware_id, status, lifecycle_state)
                    WHERE zone_id IS NOT NULL;
                ");
            }
            
            // Отдельный индекс для unassigned nodes (zone_id IS NULL)
            if (!$this->indexExists('nodes', 'nodes_unassigned_status_lifecycle_idx')) {
                DB::statement("
                    CREATE INDEX nodes_unassigned_status_lifecycle_idx 
                    ON nodes (status, lifecycle_state)
                    WHERE zone_id IS NULL;
                ");
            }
            
            // Индекс для hardware_id (используется в NodeRegistryService::registerNodeFromHello)
            if (!$this->indexExists('nodes', 'nodes_hardware_id_idx')) {
                Schema::table('nodes', function (Blueprint $table) {
                    $table->index('hardware_id', 'nodes_hardware_id_idx');
                });
            }
        }

        // 2. telemetry_last - композитный индекс для частых запросов
        if ($this->tableExists('telemetry_last')) {
            // Индекс для запросов по zone_id, metric_type, updated_at
            // Используется в TelemetryController, history-logger
            if (!$this->indexExists('telemetry_last', 'telemetry_last_zone_metric_updated_idx')) {
                DB::statement("
                    CREATE INDEX telemetry_last_zone_metric_updated_idx 
                    ON telemetry_last (zone_id, metric_type, updated_at DESC);
                ");
            }
        }

        // 3. commands - композитный индекс для частых запросов
        if ($this->tableExists('commands')) {
            // Индекс для запросов по status, zone_id, created_at
            // Используется в CommandStatusController, команды по зонам
            if (!$this->indexExists('commands', 'commands_status_zone_created_idx')) {
                DB::statement("
                    CREATE INDEX commands_status_zone_created_idx 
                    ON commands (status, zone_id, created_at DESC)
                    WHERE zone_id IS NOT NULL;
                ");
            }
            
            // Индекс для команд без zone_id (node-level commands)
            if (!$this->indexExists('commands', 'commands_status_node_created_idx')) {
                DB::statement("
                    CREATE INDEX commands_status_node_created_idx 
                    ON commands (status, node_id, created_at DESC)
                    WHERE node_id IS NOT NULL AND zone_id IS NULL;
                ");
            }
        }
    }

    /**
     * Reverse the migrations.
     */
    public function down(): void
    {
        DB::statement("DROP INDEX IF EXISTS nodes_zone_uid_hardware_status_lifecycle_idx;");
        DB::statement("DROP INDEX IF EXISTS nodes_unassigned_status_lifecycle_idx;");
        
        Schema::table('nodes', function (Blueprint $table) {
            $table->dropIndex('nodes_hardware_id_idx');
        });
        
        DB::statement("DROP INDEX IF EXISTS telemetry_last_zone_metric_updated_idx;");
        DB::statement("DROP INDEX IF EXISTS commands_status_zone_created_idx;");
        DB::statement("DROP INDEX IF EXISTS commands_status_node_created_idx;");
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
