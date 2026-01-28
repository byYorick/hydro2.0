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
     * Обновляет таблицу zone_events для Zone Event Ledger:
     * - Переименовываем details в payload_json
     * - Добавляем entity_type и entity_id
     * - Добавляем server_ts
     * - Переименовываем created_at в timestamp или оставляем как есть
     */
    public function up(): void
    {
        Schema::table('zone_events', function (Blueprint $table) {
            // Добавляем новые поля
            // entity_id может быть строкой (cmd_id) или числом (node_id, alert_id), поэтому используем text
            $table->string('entity_type')->nullable()->after('type');
            $table->string('entity_id')->nullable()->after('entity_type'); // Изменено на string для поддержки строковых ID
            $table->bigInteger('server_ts')->nullable()->after('entity_id');
            
            // Добавляем индексы для новых полей
            $table->index(['zone_id', 'entity_type', 'entity_id'], 'zone_events_zone_entity_idx');
            $table->index(['zone_id', 'id'], 'zone_events_zone_id_id_idx'); // для after_id запросов
        });
        
        // Переименовываем details в payload_json (если колонка существует)
        if (Schema::hasColumn('zone_events', 'details')) {
            DB::statement('ALTER TABLE zone_events RENAME COLUMN details TO payload_json');
        } else {
            // Если колонки details нет, добавляем payload_json
            Schema::table('zone_events', function (Blueprint $table) {
                $table->jsonb('payload_json')->nullable()->after('server_ts');
            });
        }
    }

    /**
     * Reverse the migrations.
     */
    public function down(): void
    {
        Schema::table('zone_events', function (Blueprint $table) {
            $table->dropIndex('zone_events_zone_entity_idx');
            $table->dropIndex('zone_events_zone_id_id_idx');
            $table->dropColumn(['entity_type', 'entity_id', 'server_ts']);
        });
        
        // Переименовываем обратно payload_json в details
        if (Schema::hasColumn('zone_events', 'payload_json')) {
            DB::statement('ALTER TABLE zone_events RENAME COLUMN payload_json TO details');
        }
    }
};

