<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    /**
     * Run the migrations.
     */
    public function up(): void
    {
        Schema::table('alerts', function (Blueprint $table) {
            if (!Schema::hasColumn('alerts', 'error_count')) {
                $table->integer('error_count')->default(1)->after('status');
            }
        });

        // Заполняем error_count из details.count для существующих записей
        // Это обеспечивает обратную совместимость
        // Используем проверку типа БД для совместимости с разными СУБД
        if (DB::getDriverName() === 'pgsql') {
            DB::statement("
                UPDATE alerts
                SET error_count = COALESCE(
                    CAST(details->>'count' AS INTEGER),
                    1
                )
                WHERE error_count IS NULL OR error_count = 1
            ");
        } else {
            // Для MySQL/MariaDB используем другой синтаксис
            DB::statement("
                UPDATE alerts
                SET error_count = COALESCE(
                    CAST(JSON_EXTRACT(details, '$.count') AS UNSIGNED),
                    1
                )
                WHERE error_count IS NULL OR error_count = 1
            ");
        }
    }

    /**
     * Reverse the migrations.
     */
    public function down(): void
    {
        Schema::table('alerts', function (Blueprint $table) {
            if (Schema::hasColumn('alerts', 'error_count')) {
                $table->dropColumn('error_count');
            }
        });
    }
};

