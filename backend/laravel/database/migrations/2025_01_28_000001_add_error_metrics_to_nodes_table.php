<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    /**
     * Run the migrations.
     */
    public function up(): void
    {
        // Проверяем, существует ли таблица nodes
        if (!Schema::hasTable('nodes')) {
            return; // Таблица будет создана в другой миграции
        }
        Schema::table('nodes', function (Blueprint $table) {
            // Добавляем поля для метрик ошибок, если их еще нет
            if (!Schema::hasColumn('nodes', 'error_count')) {
                $table->unsignedInteger('error_count')->default(0)->after('rssi');
            }
            if (!Schema::hasColumn('nodes', 'warning_count')) {
                $table->unsignedInteger('warning_count')->default(0)->after('error_count');
            }
            if (!Schema::hasColumn('nodes', 'critical_count')) {
                $table->unsignedInteger('critical_count')->default(0)->after('warning_count');
            }
        });
    }

    /**
     * Reverse the migrations.
     */
    public function down(): void
    {
        // Проверяем, существует ли таблица nodes
        if (!Schema::hasTable('nodes')) {
            return; // Таблица не существует, нечего откатывать
        }
        Schema::table('nodes', function (Blueprint $table) {
            if (Schema::hasColumn('nodes', 'error_count')) {
                $table->dropColumn('error_count');
            }
            if (Schema::hasColumn('nodes', 'warning_count')) {
                $table->dropColumn('warning_count');
            }
            if (Schema::hasColumn('nodes', 'critical_count')) {
                $table->dropColumn('critical_count');
            }
        });
    }
};

