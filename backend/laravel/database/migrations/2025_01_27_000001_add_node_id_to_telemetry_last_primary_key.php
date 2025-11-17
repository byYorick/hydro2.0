<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;
use Illuminate\Support\Facades\DB;

return new class extends Migration
{
    public function up(): void
    {
        // Проверяем, существует ли таблица
        if (!Schema::hasTable('telemetry_last')) {
            return; // Таблица создается в другой миграции
        }

        Schema::table('telemetry_last', function (Blueprint $table) {
            // Проверяем, существует ли старый primary key
            try {
                $table->dropPrimary(['zone_id', 'metric_type']);
            } catch (\Exception $e) {
                // Primary key может не существовать или иметь другое имя
                // Игнорируем ошибку
            }
        });
        
        // Убеждаемся, что node_id не nullable, иначе делаем его NOT NULL
        // Сначала проверим, есть ли NULL значения
        DB::statement("UPDATE telemetry_last SET node_id = -1 WHERE node_id IS NULL");
        
        Schema::table('telemetry_last', function (Blueprint $table) {
            // Делаем node_id NOT NULL
            if (Schema::hasColumn('telemetry_last', 'node_id')) {
                $table->unsignedBigInteger('node_id')->nullable(false)->change();
            }
            
            // Добавляем новый primary key с node_id
            $table->primary(['zone_id', 'node_id', 'metric_type'], 'telemetry_last_pk');
        });
    }

    public function down(): void
    {
        // Проверяем, существует ли таблица
        if (!Schema::hasTable('telemetry_last')) {
            return;
        }

        Schema::table('telemetry_last', function (Blueprint $table) {
            try {
                // Удаляем новый primary key
                $table->dropPrimary('telemetry_last_pk');
            } catch (\Exception $e) {
                // Игнорируем ошибку
            }
            
            // Возвращаем node_id в nullable
            if (Schema::hasColumn('telemetry_last', 'node_id')) {
                $table->unsignedBigInteger('node_id')->nullable()->change();
            }
            
            // Восстанавливаем старый primary key
            try {
                $table->primary(['zone_id', 'metric_type']);
            } catch (\Exception $e) {
                // Игнорируем ошибку
            }
        });
    }
};

