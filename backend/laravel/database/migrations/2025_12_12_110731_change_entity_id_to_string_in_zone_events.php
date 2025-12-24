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
     * Изменяет тип entity_id с unsignedBigInteger на string,
     * так как entity_id может быть строкой (cmd_id) или числом (node_id, alert_id).
     */
    public function up(): void
    {
        // Удаляем индекс, который использует entity_id
        Schema::table('zone_events', function (Blueprint $table) {
            $table->dropIndex('zone_events_zone_entity_idx');
        });
        
        // Изменяем тип колонки entity_id на string
        DB::statement('ALTER TABLE zone_events ALTER COLUMN entity_id TYPE text USING entity_id::text');
        
        // Восстанавливаем индекс
        Schema::table('zone_events', function (Blueprint $table) {
            $table->index(['zone_id', 'entity_type', 'entity_id'], 'zone_events_zone_entity_idx');
        });
    }

    /**
     * Reverse the migrations.
     */
    public function down(): void
    {
        Schema::table('zone_events', function (Blueprint $table) {
            $table->dropIndex('zone_events_zone_entity_idx');
        });
        
        // Возвращаем тип обратно на unsignedBigInteger
        // Внимание: это может привести к ошибкам, если есть строковые значения
        DB::statement('ALTER TABLE zone_events ALTER COLUMN entity_id TYPE bigint USING NULLIF(entity_id, \'\')::bigint');
        
        Schema::table('zone_events', function (Blueprint $table) {
            $table->index(['zone_id', 'entity_type', 'entity_id'], 'zone_events_zone_entity_idx');
        });
    }
};
