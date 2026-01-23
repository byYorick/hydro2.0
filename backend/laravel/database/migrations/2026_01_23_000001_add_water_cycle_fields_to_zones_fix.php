<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    public function up(): void
    {
        if (! Schema::hasTable('zones')) {
            return;
        }

        Schema::table('zones', function (Blueprint $table) {
            if (! Schema::hasColumn('zones', 'water_state')) {
                $table->string('water_state')->default('NORMAL_RECIRC')->after('status');
            }
            if (! Schema::hasColumn('zones', 'solution_started_at')) {
                $table->timestamp('solution_started_at')->nullable()->after('water_state');
            }
        });
    }

    public function down(): void
    {
        if (! Schema::hasTable('zones')) {
            return;
        }

        Schema::table('zones', function (Blueprint $table) {
            if (Schema::hasColumn('zones', 'solution_started_at')) {
                $table->dropColumn('solution_started_at');
            }
            if (Schema::hasColumn('zones', 'water_state')) {
                $table->dropColumn('water_state');
            }
        });
    }
};
