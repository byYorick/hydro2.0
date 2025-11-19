<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    public function up(): void
    {
        // Проверяем, существует ли таблица
        if (!Schema::hasTable('alerts')) {
            return; // Таблица создается в другой миграции
        }

        Schema::table('alerts', function (Blueprint $table) {
            if (!Schema::hasColumn('alerts', 'source')) {
                $table->string('source')->default('biz')->after('zone_id'); // biz / infra
            }
            if (!Schema::hasColumn('alerts', 'code')) {
                $table->string('code')->nullable()->after('source'); // biz_no_flow, biz_overcurrent, etc.
            }
            // type остаётся для обратной совместимости
        });
    }

    public function down(): void
    {
        Schema::table('alerts', function (Blueprint $table) {
            if (Schema::hasColumn('alerts', 'source')) {
                $table->dropColumn('source');
            }
            if (Schema::hasColumn('alerts', 'code')) {
                $table->dropColumn('code');
            }
        });
    }
};

