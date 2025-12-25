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
     * Обновление таблицы commands для двухфазного подтверждения и связи с циклами.
     * Добавляет cycle_id, context_type, request_id и обновляет структуру.
     */
    public function up(): void
    {
        Schema::table('commands', function (Blueprint $table) {
            // Добавляем связь с циклом (nullable для внецикловых команд)
            if (!Schema::hasColumn('commands', 'cycle_id')) {
                $table->foreignId('cycle_id')
                    ->nullable()
                    ->after('zone_id')
                    ->constrained('grow_cycles')
                    ->nullOnDelete();
            }
            
            // Добавляем context_type для классификации команд
            if (!Schema::hasColumn('commands', 'context_type')) {
                $table->enum('context_type', ['cycle', 'manual', 'maintenance', 'calibration'])
                    ->nullable()
                    ->after('cycle_id')
                    ->default('manual');
            }
            
            // Добавляем command_type (алиас для cmd, если нужно)
            if (!Schema::hasColumn('commands', 'command_type')) {
                $table->string('command_type')->nullable()->after('channel');
            }
            
            // Добавляем payload (алиас для params, если нужно)
            if (!Schema::hasColumn('commands', 'payload')) {
                $table->jsonb('payload')->nullable()->after('command_type');
            }
            
            // Добавляем request_id для двухфазного подтверждения
            if (!Schema::hasColumn('commands', 'request_id')) {
                $table->string('request_id', 128)
                    ->nullable()
                    ->after('cmd_id');
            }
            
            // Обновляем статусы (если нужно)
            // Статусы уже должны быть: queued|sent|accepted|executing|done|failed|timeout
            // Но проверим и обновим если нужно
        });
        
        // Добавляем уникальный индекс для request_id (если колонка была добавлена и индекса еще нет)
        if (Schema::hasColumn('commands', 'request_id') && !Schema::hasIndex('commands', 'commands_request_id_unique')) {
            Schema::table('commands', function (Blueprint $table) {
                $table->unique('request_id', 'commands_request_id_unique');
            });
        }
        
        // Добавляем индексы
        Schema::table('commands', function (Blueprint $table) {
            if (!Schema::hasIndex('commands', 'commands_cycle_idx')) {
                $table->index('cycle_id', 'commands_cycle_idx');
            }
            if (!Schema::hasIndex('commands', 'commands_request_id_idx')) {
                $table->index('request_id', 'commands_request_id_idx');
            }
            if (!Schema::hasIndex('commands', 'commands_node_status_idx')) {
                $table->index(['node_id', 'status'], 'commands_node_status_idx');
            }
        });
    }

    /**
     * Reverse the migrations.
     */
    public function down(): void
    {
        Schema::table('commands', function (Blueprint $table) {
            // Удаляем индексы
            if (Schema::hasIndex('commands', 'commands_cycle_idx')) {
                $table->dropIndex('commands_cycle_idx');
            }
            if (Schema::hasIndex('commands', 'commands_request_id_idx')) {
                $table->dropIndex('commands_request_id_idx');
            }
            if (Schema::hasIndex('commands', 'commands_node_status_idx')) {
                $table->dropIndex('commands_node_status_idx');
            }
            
            // Удаляем индексы
            if (Schema::hasIndex('commands', 'commands_cycle_idx')) {
                $table->dropIndex('commands_cycle_idx');
            }
            if (Schema::hasIndex('commands', 'commands_request_id_idx')) {
                $table->dropIndex('commands_request_id_idx');
            }
            if (Schema::hasIndex('commands', 'commands_node_status_idx')) {
                $table->dropIndex('commands_node_status_idx');
            }
            
            // Удаляем уникальный индекс для request_id
            if (Schema::hasIndex('commands', 'commands_request_id_unique')) {
                $table->dropUnique('commands_request_id_unique');
            }
            
            // Удаляем новые колонки
            if (Schema::hasColumn('commands', 'cycle_id')) {
                $table->dropForeign(['cycle_id']);
                $table->dropColumn('cycle_id');
            }
            if (Schema::hasColumn('commands', 'context_type')) {
                $table->dropColumn('context_type');
            }
            if (Schema::hasColumn('commands', 'request_id')) {
                $table->dropColumn('request_id');
            }
            if (Schema::hasColumn('commands', 'command_type')) {
                $table->dropColumn('command_type');
            }
            if (Schema::hasColumn('commands', 'payload')) {
                $table->dropColumn('payload');
            }
            
            // Восстанавливаем старые названия (если были переименованы)
            if (Schema::hasColumn('commands', 'command_type') && !Schema::hasColumn('commands', 'cmd')) {
                $table->renameColumn('command_type', 'cmd');
            }
            if (Schema::hasColumn('commands', 'payload') && !Schema::hasColumn('commands', 'params')) {
                $table->renameColumn('payload', 'params');
            }
        });
    }
};

