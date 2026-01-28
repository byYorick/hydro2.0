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
        Schema::table('pending_alerts', function (Blueprint $table) {
            $table->timestampTz('next_retry_at')->nullable()->after('max_attempts');
            $table->index(['next_retry_at'], 'pending_alerts_next_retry_at_idx');
        });
    }

    /**
     * Reverse the migrations.
     */
    public function down(): void
    {
        Schema::table('pending_alerts', function (Blueprint $table) {
            $table->dropIndex('pending_alerts_next_retry_at_idx');
            $table->dropColumn('next_retry_at');
        });
    }
};
