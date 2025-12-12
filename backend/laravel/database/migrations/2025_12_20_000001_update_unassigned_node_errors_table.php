<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;
use Illuminate\Support\Facades\DB;

return new class extends Migration
{
    public function up(): void
    {
        Schema::table('unassigned_node_errors', function (Blueprint $table) {
            // Удаляем старый unique constraint
            $table->dropUnique('unassigned_errors_hardware_topic_unique');
            
            // Удаляем старый индекс
            $table->dropIndex('unassigned_errors_hardware_error_idx');
        });
        
        // Переименовываем error_level в severity
        DB::statement('ALTER TABLE unassigned_node_errors RENAME COLUMN error_level TO severity');
        
        // Переименовываем error_data в last_payload
        DB::statement('ALTER TABLE unassigned_node_errors RENAME COLUMN error_data TO last_payload');
        
        // Создаем функциональный уникальный индекс для hardware_id + COALESCE(error_code, '')
        DB::statement('CREATE UNIQUE INDEX unassigned_errors_hardware_code_unique ON unassigned_node_errors (hardware_id, COALESCE(error_code, \'\'))');
        
        Schema::table('unassigned_node_errors', function (Blueprint $table) {
            // Создаем индекс на hardware_id + error_code
            $table->index(['hardware_id', 'error_code'], 'unassigned_errors_hardware_code_idx');
        });
    }

    public function down(): void
    {
        // Удаляем функциональный индекс
        DB::statement('DROP INDEX IF EXISTS unassigned_errors_hardware_code_unique');
        
        Schema::table('unassigned_node_errors', function (Blueprint $table) {
            // Удаляем индекс
            $table->dropIndex('unassigned_errors_hardware_code_idx');
        });
        
        // Возвращаем старые названия
        DB::statement('ALTER TABLE unassigned_node_errors RENAME COLUMN severity TO error_level');
        DB::statement('ALTER TABLE unassigned_node_errors RENAME COLUMN last_payload TO error_data');
        
        Schema::table('unassigned_node_errors', function (Blueprint $table) {
            // Восстанавливаем старый unique constraint
            $table->unique(['hardware_id', 'topic'], 'unassigned_errors_hardware_topic_unique');
            
            // Восстанавливаем старый индекс
            $table->index(['hardware_id', 'error_code'], 'unassigned_errors_hardware_error_idx');
        });
    }
};

