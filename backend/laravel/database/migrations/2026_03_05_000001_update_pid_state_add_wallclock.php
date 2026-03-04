<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    public function up(): void
    {
        Schema::table('pid_state', function (Blueprint $table) {
            $table->timestampTz('last_dose_at')->nullable()->after('last_output_ms');
            $table->float('prev_derivative')->default(0.0)->after('prev_error');
        });
    }

    public function down(): void
    {
        Schema::table('pid_state', function (Blueprint $table) {
            $table->dropColumn(['last_dose_at', 'prev_derivative']);
        });
    }
};
