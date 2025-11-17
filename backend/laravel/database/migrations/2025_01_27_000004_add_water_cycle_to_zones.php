<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    public function up(): void
    {
        // Проверяем, существует ли таблица
        if (!Schema::hasTable('zones')) {
            return; // Таблица создается в другой миграции
        }

        Schema::table('zones', function (Blueprint $table) {
            if (!Schema::hasColumn('zones', 'water_state')) {
                $table->string('water_state')->default('NORMAL_RECIRC')->after('status');
                // NORMAL_RECIRC / WATER_CHANGE_DRAIN / WATER_CHANGE_FILL / WATER_CHANGE_STABILIZE
            }
            if (!Schema::hasColumn('zones', 'solution_started_at')) {
                $table->timestamp('solution_started_at')->nullable()->after('water_state');
            }
        });
    }

    public function down(): void
    {
        // Проверяем, существует ли таблица
        if (!Schema::hasTable('zones')) {
            return;
        }

        Schema::table('zones', function (Blueprint $table) {
            if (Schema::hasColumn('zones', 'water_state')) {
                $table->dropColumn('water_state');
            }
            if (Schema::hasColumn('zones', 'solution_started_at')) {
                $table->dropColumn('solution_started_at');
            }
        });
    }
};


