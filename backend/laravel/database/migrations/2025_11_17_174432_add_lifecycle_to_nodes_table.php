<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    public function up(): void
    {
        Schema::table('nodes', function (Blueprint $table) {
            if (!Schema::hasColumn('nodes', 'lifecycle_state')) {
                $table->string('lifecycle_state', 32)->default('UNPROVISIONED')->after('status');
                // MANUFACTURED, UNPROVISIONED, PROVISIONED_WIFI, REGISTERED_BACKEND, ASSIGNED_TO_ZONE, ACTIVE, DEGRADED, MAINTENANCE, DECOMMISSIONED
            }
            if (!Schema::hasColumn('nodes', 'hardware_id')) {
                $table->string('hardware_id', 128)->nullable()->unique()->after('uid');
                // MAC-адрес или серийный номер устройства
            }
            
            // Индекс на hardware_id уже создаётся через unique()
            // Можно добавить индекс на lifecycle_state для быстрого поиска
            if (!$this->hasIndex('nodes', 'nodes_lifecycle_state_idx')) {
                $table->index('lifecycle_state', 'nodes_lifecycle_state_idx');
            }
        });
    }

    public function down(): void
    {
        Schema::table('nodes', function (Blueprint $table) {
            if (Schema::hasColumn('nodes', 'lifecycle_state')) {
                $table->dropIndex('nodes_lifecycle_state_idx');
                $table->dropColumn('lifecycle_state');
            }
            if (Schema::hasColumn('nodes', 'hardware_id')) {
                $table->dropUnique(['hardware_id']);
                $table->dropColumn('hardware_id');
            }
        });
    }
    
    /**
     * Проверить наличие индекса в таблице.
     */
    private function hasIndex(string $table, string $indexName): bool
    {
        $connection = Schema::getConnection();
        $databaseName = $connection->getDatabaseName();
        
        $result = $connection->selectOne(
            "SELECT COUNT(*) as count 
             FROM pg_indexes 
             WHERE schemaname = 'public' 
             AND tablename = ? 
             AND indexname = ?",
            [$table, $indexName]
        );
        
        return $result && $result->count > 0;
    }
};
