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
        Schema::table('grow_cycles', function (Blueprint $table) {
            if (! Schema::hasColumn('grow_cycles', 'current_stage_code')) {
                $table->string('current_stage_code', 32)->nullable()->after('current_phase_id');
            }

            if (! Schema::hasColumn('grow_cycles', 'current_stage_started_at')) {
                $table->timestamp('current_stage_started_at')->nullable()->after('current_stage_code');
            }
        });
    }

    /**
     * Reverse the migrations.
     */
    public function down(): void
    {
        Schema::table('grow_cycles', function (Blueprint $table) {
            if (Schema::hasColumn('grow_cycles', 'current_stage_started_at')) {
                $table->dropColumn('current_stage_started_at');
            }

            if (Schema::hasColumn('grow_cycles', 'current_stage_code')) {
                $table->dropColumn('current_stage_code');
            }
        });
    }
};
