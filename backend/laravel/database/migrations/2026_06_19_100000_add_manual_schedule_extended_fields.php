<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    public function up(): void
    {
        if (! Schema::hasTable('zone_manual_schedules')) {
            return;
        }

        Schema::table('zone_manual_schedules', function (Blueprint $table) {
            if (! Schema::hasColumn('zone_manual_schedules', 'days_of_week')) {
                $table->jsonb('days_of_week')->nullable()->after('window_end');
            }
            if (! Schema::hasColumn('zone_manual_schedules', 'run_at')) {
                $table->timestampTz('run_at')->nullable()->after('days_of_week');
            }
            if (! Schema::hasColumn('zone_manual_schedules', 'last_dispatched_at')) {
                $table->timestampTz('last_dispatched_at')->nullable()->after('run_at');
            }
        });
    }

    public function down(): void
    {
        if (! Schema::hasTable('zone_manual_schedules')) {
            return;
        }

        Schema::table('zone_manual_schedules', function (Blueprint $table) {
            if (Schema::hasColumn('zone_manual_schedules', 'last_dispatched_at')) {
                $table->dropColumn('last_dispatched_at');
            }
            if (Schema::hasColumn('zone_manual_schedules', 'run_at')) {
                $table->dropColumn('run_at');
            }
            if (Schema::hasColumn('zone_manual_schedules', 'days_of_week')) {
                $table->dropColumn('days_of_week');
            }
        });
    }
};
